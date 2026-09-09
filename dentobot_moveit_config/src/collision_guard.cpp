#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <limits>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <moveit/collision_detection/collision_common.hpp>
#include <moveit/planning_scene_monitor/planning_scene_monitor.hpp>
#include <moveit/robot_model_loader/robot_model_loader.hpp>
#include <moveit/robot_model/joint_model.hpp>
#include <moveit/robot_state/robot_state.hpp>
#include <geometric_shapes/shapes.h>
#include <json/json.h>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/float64_multi_array.hpp>
#include <std_msgs/msg/string.hpp>

namespace
{
constexpr char STATUS_SCHEMA[] = "dentobot.joint_command_status.v1";
constexpr char TASK_CONFIG_SCHEMA[] = "dentobot.task_guard_config.v3";
constexpr char TASK_COMMAND_SCHEMA[] = "dentobot.task_joint_command.v2";
constexpr char TASK_STATUS_SCHEMA[] = "dentobot.task_joint_status.v2";
constexpr double CLEARANCE_COMPARISON_EPSILON_M = 1e-9;
constexpr double SIMULATION_GUIDE_CLEARANCE_M = 0.0001;
constexpr double SIMULATION_GUIDE_CONTACT_MAX_PENETRATION_M = 0.0005;
constexpr double CORRIDOR_ENDPOINT_EPSILON_M = 0.00025;
// Match the Step 6 provisional-TCP/FK acceptance tolerance. Smaller values
// reject harmless KDL/trajectory-parameterization jitter below the 0.3 mm case
// surface resolution; larger reversals remain blocked.
constexpr double CORRIDOR_MONOTONIC_EPSILON_M = 0.00025;

std::string json_escape(const std::string& value)
{
  std::ostringstream output;
  for (const unsigned char character : value)
  {
    switch (character)
    {
      case '\\': output << "\\\\"; break;
      case '"': output << "\\\""; break;
      case '\b': output << "\\b"; break;
      case '\f': output << "\\f"; break;
      case '\n': output << "\\n"; break;
      case '\r': output << "\\r"; break;
      case '\t': output << "\\t"; break;
      default:
        if (character < 0x20)
        {
          output << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                 << static_cast<int>(character) << std::dec;
        }
        else
        {
          output << character;
        }
    }
  }
  return output.str();
}

std::string json_number(double value)
{
  if (!std::isfinite(value))
  {
    return "null";
  }
  std::ostringstream output;
  output << std::setprecision(12) << value;
  return output.str();
}

std::string json_array(const std::vector<double>& values)
{
  std::ostringstream output;
  output << '[';
  for (std::size_t index = 0; index < values.size(); ++index)
  {
    if (index > 0)
    {
      output << ',';
    }
    output << json_number(values[index]);
  }
  output << ']';
  return output.str();
}

std::string json_point_or_null(
  const std::array<double, 3>& point, const bool available)
{
  if (!available)
  {
    return "null";
  }
  return "[" + json_number(point[0]) + "," + json_number(point[1]) + "," +
         json_number(point[2]) + "]";
}

bool json_string_field(
  const Json::Value& payload, const std::string& key, std::string& value)
{
  if (!payload.isMember(key) || !payload[key].isString())
  {
    return false;
  }
  value = payload[key].asString();
  return true;
}

bool json_number_field(
  const Json::Value& payload, const std::string& key, double& value)
{
  if (!payload.isMember(key) || !payload[key].isNumeric())
  {
    return false;
  }
  try
  {
    value = payload[key].asDouble();
  }
  catch (const std::exception&)
  {
    return false;
  }
  return std::isfinite(value);
}

bool json_integer_field(
  const Json::Value& payload, const std::string& key, std::int64_t& value)
{
  if (!payload.isMember(key) ||
      (!payload[key].isInt64() && !payload[key].isUInt64()))
  {
    return false;
  }
  try
  {
    value = payload[key].asInt64();
  }
  catch (const std::exception&)
  {
    return false;
  }
  return true;
}

bool json_number_array_field(
  const Json::Value& payload, const std::string& key, std::vector<double>& values)
{
  if (!payload.isMember(key) || !payload[key].isArray())
  {
    return false;
  }
  values.clear();
  for (const auto& item : payload[key])
  {
    if (!item.isNumeric())
    {
      return false;
    }
    try
    {
      const double value = item.asDouble();
      if (!std::isfinite(value))
      {
        return false;
      }
      values.push_back(value);
    }
    catch (const std::exception&)
    {
      return false;
    }
  }
  return true;
}

bool json_string_array_field(
  const Json::Value& payload, const std::string& key, std::vector<std::string>& values)
{
  if (!payload.isMember(key) || !payload[key].isArray())
  {
    return false;
  }
  values.clear();
  for (const auto& item : payload[key])
  {
    if (!item.isString())
    {
      return false;
    }
    values.push_back(item.asString());
  }
  return true;
}

bool parse_json_object(
  const std::string& payload, Json::Value& document, std::string& reason)
{
  Json::CharReaderBuilder builder;
  builder["collectComments"] = false;
  std::unique_ptr<Json::CharReader> reader(builder.newCharReader());
  std::string errors;
  if (!reader->parse(
        payload.data(), payload.data() + payload.size(), &document, &errors))
  {
    reason = "Malformed JSON: " + errors;
    return false;
  }
  if (!document.isObject())
  {
    reason = "Payload must be a JSON object.";
    return false;
  }
  return true;
}

struct TaskGuardConfig
{
  bool valid{ false };
  std::string task_fingerprint;
  std::string guard_session_id;
  std::string target_object_id;
  std::string allowed_robot_link;
  std::vector<std::string> clearance_exempt_object_ids;
  std::vector<std::string> simulation_guide_clearance_object_ids;
  std::string tool_tip_frame;
  Eigen::Vector3d entry_base_m{ Eigen::Vector3d::Zero() };
  Eigen::Vector3d target_base_m{ Eigen::Vector3d::Zero() };
  double corridor_radius_m{ 0.0 };
  double approach_standoff_m{ 0.0 };
};

struct TaskJointCommand
{
  std::string task_fingerprint;
  std::string guard_session_id;
  std::string phase;
  std::int64_t sequence{ -1 };
  std::vector<double> joint_positions;
  bool validate_only{ false };
};

struct WorldObjectEvidence
{
  std::string id;
  std::size_t shape_count{ 0 };
  std::array<double, 7> pose_xyzw{ { 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0 } };
  std::array<double, 6> bounds_m{ {
    std::numeric_limits<double>::infinity(),
    -std::numeric_limits<double>::infinity(),
    std::numeric_limits<double>::infinity(),
    -std::numeric_limits<double>::infinity(),
    std::numeric_limits<double>::infinity(),
    -std::numeric_limits<double>::infinity()
  } };
  bool has_mesh_bounds{ false };
};

struct GuardResult
{
  bool accepted{ false };
  std::string reason;
  std::size_t checked_samples{ 0 };
  double minimum_self_distance_m{ std::numeric_limits<double>::infinity() };
  double minimum_world_distance_m{ std::numeric_limits<double>::infinity() };
  std::string first_body;
  std::string second_body;
  std::array<double, 3> nearest_point_first_base_m{ { 0.0, 0.0, 0.0 } };
  std::array<double, 3> nearest_point_second_base_m{ { 0.0, 0.0, 0.0 } };
  bool nearest_points_available{ false };
  std::size_t world_object_count{ 0 };
  std::vector<WorldObjectEvidence> world_objects;
  bool corridor_ok{ false };
  double corridor_progress{ std::numeric_limits<double>::quiet_NaN() };
  double corridor_distance_m{ std::numeric_limits<double>::quiet_NaN() };
  bool exploratory_tool_contact_suppressed{ false };
  std::size_t suppressed_tool_contact_sample_count{ 0 };
  bool guide_clearance_warning{ false };
  std::size_t guide_clearance_warning_sample_count{ 0 };
  double minimum_guide_clearance_warning_m{ std::numeric_limits<double>::quiet_NaN() };
  std::string guide_clearance_warning_robot_link;
  std::string guide_clearance_warning_object_id;
  std::string guide_warning_kind;
  double guide_clearance_warning_contact_penetration_m{
    std::numeric_limits<double>::quiet_NaN() };
  std::size_t guide_clearance_warning_contact_sample_count{ 0 };
  std::array<double, 3> guide_clearance_warning_contact_position_base_m{
    { 0.0, 0.0, 0.0 } };
  bool guide_clearance_warning_contact_position_available{ false };
};
}  // namespace

class DentobotCollisionGuard : public rclcpp::Node
{
public:
  DentobotCollisionGuard()
    : Node("dentobot_collision_guard")
  {
    group_name_ = declare_parameter<std::string>("group_name", "dentobot_arm");
    raw_command_topic_ = declare_parameter<std::string>(
      "raw_command_topic", "/dentobot/slicer_joint_positions");
    accepted_command_topic_ = declare_parameter<std::string>(
      "accepted_command_topic", "/dentobot/validated_joint_positions");
    status_topic_ = declare_parameter<std::string>(
      "status_topic", "/dentobot/joint_command_status");
    task_config_topic_ = declare_parameter<std::string>(
      "task_config_topic", "/dentobot/task_guard_config");
    task_command_topic_ = declare_parameter<std::string>(
      "task_command_topic", "/dentobot/task_joint_command");
    task_status_topic_ = declare_parameter<std::string>(
      "task_status_topic", "/dentobot/task_joint_status");
    minimum_clearance_m_ = declare_parameter<double>("minimum_clearance_m", 0.001);
    maximum_revolute_step_rad_ = declare_parameter<double>(
      "maximum_revolute_step_rad", 0.017453292519943295);
    maximum_prismatic_step_m_ = declare_parameter<double>(
      "maximum_prismatic_step_m", 0.0005);
    maximum_interpolation_samples_ = declare_parameter<int>(
      "maximum_interpolation_samples", 1000);

    if (group_name_.empty() || raw_command_topic_.empty() ||
        accepted_command_topic_.empty() || status_topic_.empty() ||
        task_config_topic_.empty() || task_command_topic_.empty() ||
        task_status_topic_.empty())
    {
      throw std::invalid_argument("collision-guard names and topics must be non-empty");
    }
    if (!std::isfinite(minimum_clearance_m_) || minimum_clearance_m_ < 0.0 ||
        !std::isfinite(maximum_revolute_step_rad_) || maximum_revolute_step_rad_ <= 0.0 ||
        !std::isfinite(maximum_prismatic_step_m_) || maximum_prismatic_step_m_ <= 0.0 ||
        maximum_interpolation_samples_ < 1)
    {
      throw std::invalid_argument("collision-guard distances and interpolation limits are invalid");
    }
  }

  void initialize()
  {
    auto robot_model_loader = std::make_shared<robot_model_loader::RobotModelLoader>(
      shared_from_this(), "robot_description", false);
    planning_scene_monitor_ = std::make_shared<planning_scene_monitor::PlanningSceneMonitor>(
      shared_from_this(), robot_model_loader, "dentobot_collision_guard_scene");
    if (!planning_scene_monitor_->getPlanningScene() ||
        !planning_scene_monitor_->getRobotModel())
    {
      throw std::runtime_error("MoveIt could not construct the DENTOBOT planning scene");
    }
    robot_model_ = planning_scene_monitor_->getRobotModel();
    joint_model_group_ = robot_model_->getJointModelGroup(group_name_);
    if (joint_model_group_ == nullptr)
    {
      throw std::runtime_error("MoveIt group does not exist: " + group_name_);
    }
    joint_names_ = joint_model_group_->getVariableNames();
    if (joint_names_.empty())
    {
      throw std::runtime_error("MoveIt group has no commandable joint variables");
    }
    moveit::core::RobotState initial_state(robot_model_);
    initial_state.setToDefaultValues();
    initial_state.copyJointGroupPositions(joint_model_group_, last_accepted_positions_);

    accepted_publisher_ = create_publisher<std_msgs::msg::Float64MultiArray>(
      accepted_command_topic_, 10);
    status_publisher_ = create_publisher<std_msgs::msg::String>(status_topic_, 10);
    task_status_publisher_ = create_publisher<std_msgs::msg::String>(
      task_status_topic_, 10);
    command_subscription_ = create_subscription<std_msgs::msg::Float64MultiArray>(
      raw_command_topic_, 10,
      std::bind(&DentobotCollisionGuard::on_command, this, std::placeholders::_1));
    task_config_subscription_ = create_subscription<std_msgs::msg::String>(
      task_config_topic_, 10,
      std::bind(&DentobotCollisionGuard::on_task_config, this, std::placeholders::_1));
    task_command_subscription_ = create_subscription<std_msgs::msg::String>(
      task_command_topic_, 10,
      std::bind(&DentobotCollisionGuard::on_task_command, this, std::placeholders::_1));
    heartbeat_timer_ = create_wall_timer(
      std::chrono::milliseconds(500),
      std::bind(&DentobotCollisionGuard::publish_last_status, this));

    // PlanningSceneMonitor advertises its own maintained-scene publisher during
    // construction. The guard is read-only: move_group is the sole authority.
    planning_scene_monitor_->stopPublishingPlanningScene();
    // Slicer publishes CollisionObject messages directly. Monitoring that
    // authoritative input avoids a second copy/feedback path through
    // move_group's monitored_planning_scene topic.
    planning_scene_monitor_->startWorldGeometryMonitor(
      planning_scene_monitor::PlanningSceneMonitor::DEFAULT_COLLISION_OBJECT_TOPIC,
      planning_scene_monitor::PlanningSceneMonitor::DEFAULT_PLANNING_SCENE_WORLD_TOPIC,
      false);
    planning_scene_monitor_->startStateMonitor("/joint_states");

    GuardResult initial_result = validate_motion(
      last_accepted_positions_, last_accepted_positions_);
    if (!initial_result.accepted)
    {
      throw std::runtime_error(
        "The URDF/SRDF default state failed the collision guard: " +
        initial_result.reason);
    }
    initial_result.reason =
      "Initialized after validating the URDF/SRDF default state; subsequent commands are collision gated.";
    last_status_json_ = status_json(
      initial_result, last_accepted_positions_, last_accepted_positions_);
    publish_accepted(last_accepted_positions_);
    publish_last_status();

    RCLCPP_INFO(
      get_logger(),
      "Collision guard ready: group=%s, self/world clearance=%.3f m, "
      "interpolation steps=(%.6f rad, %.6f m). Simulation only.",
      group_name_.c_str(), minimum_clearance_m_, maximum_revolute_step_rad_,
      maximum_prismatic_step_m_);
  }

private:
  void on_command(const std_msgs::msg::Float64MultiArray::SharedPtr message)
  {
    const std::vector<double> requested(message->data.begin(), message->data.end());
    GuardResult result;
    if (requested.size() != joint_names_.size())
    {
      if (requested.size() == joint_names_.size() + 1)
      {
        result.reason =
          "Received a legacy six-joint command; the external spindle is not a "
          "planning DOF. Send five ordered planning joint values.";
      }
      else
      {
        result.reason = "Expected " + std::to_string(joint_names_.size()) +
                        " joint values, received " + std::to_string(requested.size()) + ".";
      }
    }
    else if (!std::all_of(requested.begin(), requested.end(),
                          [](double value) { return std::isfinite(value); }))
    {
      result.reason = "A requested joint value is not finite.";
    }
    else
    {
      result = validate_motion(last_accepted_positions_, requested);
    }

    if (result.accepted)
    {
      last_accepted_positions_ = requested;
      publish_accepted(last_accepted_positions_);
    }
    last_status_json_ = status_json(result, requested, last_accepted_positions_);
    publish_last_status();
  }

  bool parse_task_config(const std::string& payload, TaskGuardConfig& config, std::string& reason)
  {
    Json::Value document;
    if (!parse_json_object(payload, document, reason))
    {
      reason = "Malformed task-guard configuration: " + reason;
      return false;
    }
    std::string schema;
    std::string mode;
    std::vector<double> entry;
    std::vector<double> target;
    const auto malformed = [&reason](const std::string& field) {
      reason = "Malformed or unsupported task-guard field: " + field + ".";
      return false;
    };
    if (!json_string_field(document, "schema", schema) || schema != TASK_CONFIG_SCHEMA)
      return malformed("schema");
    if (!json_string_field(document, "mode", mode) || mode != "simulation_only")
      return malformed("mode");
    if (!json_string_field(document, "task_fingerprint", config.task_fingerprint))
      return malformed("task_fingerprint");
    if (!json_string_field(document, "guard_session_id", config.guard_session_id))
      return malformed("guard_session_id");
    if (!json_string_field(document, "target_object_id", config.target_object_id))
      return malformed("target_object_id");
    if (!json_string_field(document, "allowed_robot_link", config.allowed_robot_link))
      return malformed("allowed_robot_link");
    if (!json_string_array_field(
          document, "clearance_exempt_object_ids", config.clearance_exempt_object_ids))
      return malformed("clearance_exempt_object_ids");
    if (config.allowed_robot_link != "burr" ||
        std::any_of(config.clearance_exempt_object_ids.begin(),
                    config.clearance_exempt_object_ids.end(),
                    [&config](const std::string& id) {
                      return id != config.target_object_id;
                    }))
    {
      reason = "Only the selected target may receive a burr-contact allowance.";
      return false;
    }
    std::vector<std::string> retired_guide_links;
    std::vector<std::string> retired_guide_objects;
    if (document.isMember("guide_clearance_exempt_robot_links") &&
        !json_string_array_field(
          document, "guide_clearance_exempt_robot_links", retired_guide_links))
      return malformed("guide_clearance_exempt_robot_links");
    if (document.isMember("guide_clearance_exempt_object_ids") &&
        !json_string_array_field(
          document, "guide_clearance_exempt_object_ids", retired_guide_objects))
      return malformed("guide_clearance_exempt_object_ids");
    if (!retired_guide_links.empty() || !retired_guide_objects.empty())
    {
      reason =
        "Task-guard guide/template clearance exemption fields are retired and "
        "rejected; use simulation_guide_clearance_object_ids.";
      return false;
    }
    if (document.isMember("simulation_guide_clearance_object_ids") &&
        !json_string_array_field(
          document, "simulation_guide_clearance_object_ids",
          config.simulation_guide_clearance_object_ids))
      return malformed("simulation_guide_clearance_object_ids");
    if (!json_string_field(document, "tool_tip_frame", config.tool_tip_frame))
      return malformed("tool_tip_frame");
    if (!json_number_array_field(document, "entry_base_m", entry) || entry.size() != 3)
      return malformed("entry_base_m");
    if (!json_number_array_field(document, "target_base_m", target) || target.size() != 3)
      return malformed("target_base_m");
    if (!json_number_field(document, "corridor_radius_m", config.corridor_radius_m))
      return malformed("corridor_radius_m");
    if (!json_number_field(document, "approach_standoff_m", config.approach_standoff_m))
      return malformed("approach_standoff_m");
    if (config.task_fingerprint.empty() || config.guard_session_id.empty() ||
        config.target_object_id.empty() ||
        config.allowed_robot_link.empty() || config.tool_tip_frame.empty() ||
        config.corridor_radius_m <= 0.0 || config.approach_standoff_m <= 0.0)
    {
      reason = "Task-guard identities and dimensions must be non-empty and positive.";
      return false;
    }
    if (!robot_model_->hasLinkModel(config.allowed_robot_link) ||
        !robot_model_->hasLinkModel(config.tool_tip_frame))
    {
      reason = "Task-guard robot link or provisional drill-tip frame does not exist.";
      return false;
    }
    if (std::any_of(
          config.clearance_exempt_object_ids.begin(),
          config.clearance_exempt_object_ids.end(),
          [](const std::string& value) { return value.empty(); }))
    {
      reason = "Task-guard clearance-exempt object identities must be non-empty.";
      return false;
    }
    if (std::any_of(
          config.simulation_guide_clearance_object_ids.begin(),
          config.simulation_guide_clearance_object_ids.end(),
          [](const std::string& value) { return value.empty(); }))
    {
      reason = "Task-guard simulation guide-clearance object identities must be non-empty.";
      return false;
    }
    if (std::any_of(
          config.simulation_guide_clearance_object_ids.begin(),
          config.simulation_guide_clearance_object_ids.end(),
          [&config](const std::string& value) {
            return value == config.target_object_id;
          }))
    {
      reason =
        "Task-guard simulation guide-clearance objects must not include the selected target.";
      return false;
    }
    std::sort(
      config.simulation_guide_clearance_object_ids.begin(),
      config.simulation_guide_clearance_object_ids.end());
    if (std::adjacent_find(
          config.simulation_guide_clearance_object_ids.begin(),
          config.simulation_guide_clearance_object_ids.end()) !=
        config.simulation_guide_clearance_object_ids.end())
    {
      reason = "Task-guard simulation guide-clearance object identities must be unique.";
      return false;
    }
    std::sort(
      config.clearance_exempt_object_ids.begin(),
      config.clearance_exempt_object_ids.end());
    config.clearance_exempt_object_ids.erase(
      std::unique(
        config.clearance_exempt_object_ids.begin(),
        config.clearance_exempt_object_ids.end()),
      config.clearance_exempt_object_ids.end());
    config.entry_base_m = Eigen::Vector3d(entry[0], entry[1], entry[2]);
    config.target_base_m = Eigen::Vector3d(target[0], target[1], target[2]);
    if ((config.target_base_m - config.entry_base_m).norm() <= 1e-9)
    {
      reason = "Task-guard Entry and Target must define a non-zero corridor.";
      return false;
    }
    config.valid = true;
    return true;
  }

  bool parse_task_command(const std::string& payload, TaskJointCommand& command, std::string& reason)
  {
    Json::Value document;
    if (!parse_json_object(payload, document, reason))
    {
      reason = "Malformed phased command: " + reason;
      return false;
    }
    std::string schema;
    std::string mode;
    if (!json_string_field(document, "schema", schema) || schema != TASK_COMMAND_SCHEMA ||
        !json_string_field(document, "mode", mode) || mode != "simulation_only" ||
        !json_string_field(document, "task_fingerprint", command.task_fingerprint) ||
        !json_string_field(document, "guard_session_id", command.guard_session_id) ||
        !json_string_field(document, "phase", command.phase) ||
        !json_integer_field(document, "sequence", command.sequence) ||
        !json_number_array_field(document, "joint_positions", command.joint_positions))
    {
      reason = "Malformed or unsupported phased joint command.";
      return false;
    }
    if (command.task_fingerprint.empty() || command.guard_session_id.empty() ||
        command.sequence < 0 ||
        (command.phase != "approach" && command.phase != "terminal_contact" &&
         command.phase != "drilling" && command.phase != "retraction"))
    {
      reason = "Phased command identity, phase, or sequence is invalid.";
      return false;
    }
    if (command.joint_positions.size() != joint_names_.size() ||
        !std::all_of(command.joint_positions.begin(), command.joint_positions.end(),
                     [](double value) { return std::isfinite(value); }))
    {
      if (command.joint_positions.size() == joint_names_.size() + 1)
      {
        reason =
          "Phased command contains a legacy spindle value; the external spindle is "
          "not a planning DOF. Send five ordered planning joint values.";
      }
      else
      {
        reason = "Phased command must contain five finite ordered planning joint values.";
      }
      return false;
    }
    if (document.isMember("validate_only"))
    {
      if (!document["validate_only"].isBool())
      {
        reason = "Phased command validate_only flag must be Boolean.";
        return false;
      }
      command.validate_only = document["validate_only"].asBool();
    }
    return true;
  }

  void on_task_config(const std_msgs::msg::String::SharedPtr message)
  {
    TaskGuardConfig candidate;
    std::string reason;
    if (!parse_task_config(message->data, candidate, reason))
    {
      task_config_ = TaskGuardConfig{};
      active_task_config_payload_.clear();
      last_task_sequence_ = -1;
      RCLCPP_WARN(get_logger(), "%s", reason.c_str());
      return;
    }
    if (task_config_.valid &&
        candidate.guard_session_id == task_config_.guard_session_id)
    {
      if (message->data == active_task_config_payload_)
      {
        // The Python side retries configuration until its sequence-zero
        // handshake is acknowledged. Repeated delivery of the exact same
        // session must not reset sequence or corridor history.
        return;
      }
      task_config_ = TaskGuardConfig{};
      active_task_config_payload_.clear();
      last_task_sequence_ = -1;
      RCLCPP_WARN(
        get_logger(),
        "Rejected changed task-guard data that reused guard session %s.",
        candidate.guard_session_id.c_str());
      return;
    }
    task_config_ = candidate;
    active_task_config_payload_ = message->data;
    last_task_sequence_ = -1;
    last_corridor_progress_m_ = -candidate.approach_standoff_m;
    preflight_positions_ = last_accepted_positions_;
    last_preflight_sequence_ = -1;
    last_preflight_corridor_progress_m_ = -candidate.approach_standoff_m;
    RCLCPP_INFO(
      get_logger(), "Accepted simulation task guard %s session %s for target %s.",
      candidate.task_fingerprint.c_str(), candidate.guard_session_id.c_str(),
      candidate.target_object_id.c_str());
  }

  void on_task_command(const std_msgs::msg::String::SharedPtr message)
  {
    TaskJointCommand command;
    GuardResult result;
    std::string parse_reason;
    if (!parse_task_command(message->data, command, parse_reason))
    {
      result.reason = parse_reason;
    }
    else if (!task_config_.valid)
    {
      result.reason = "No valid simulation task-guard configuration is active.";
    }
    else if (command.task_fingerprint != task_config_.task_fingerprint)
    {
      result.reason = "Command task fingerprint does not match the active immutable task.";
    }
    else if (command.guard_session_id != task_config_.guard_session_id)
    {
      result.reason = "Command guard session does not match the active preview session.";
    }
    else if (command.sequence <= (command.validate_only ?
                                  last_preflight_sequence_ : last_task_sequence_))
    {
      result.reason = "Phased command sequence is stale or duplicated.";
    }
    else
    {
      const std::vector<double>& start_positions = command.validate_only ?
        preflight_positions_ : last_accepted_positions_;
      const double prior_progress = command.validate_only ?
        last_preflight_corridor_progress_m_ : last_corridor_progress_m_;
      result = validate_motion(
        start_positions, command.joint_positions, &task_config_, command.phase,
        prior_progress);
    }

    if (result.accepted)
    {
      if (command.validate_only)
      {
        preflight_positions_ = command.joint_positions;
        last_preflight_sequence_ = command.sequence;
        if (command.phase == "terminal_contact" || command.phase == "drilling" ||
            command.phase == "retraction")
        {
          last_preflight_corridor_progress_m_ = result.corridor_progress;
        }
      }
      else
      {
        last_accepted_positions_ = command.joint_positions;
        last_task_sequence_ = command.sequence;
        if (command.phase == "terminal_contact" || command.phase == "drilling" ||
            command.phase == "retraction")
        {
          last_corridor_progress_m_ = result.corridor_progress;
        }
        publish_accepted(last_accepted_positions_);
      }
    }
    publish_task_status(result, command);
  }

  GuardResult validate_motion(
    const std::vector<double>& start_positions,
    const std::vector<double>& target_positions,
    const TaskGuardConfig* task_config = nullptr,
    const std::string& phase = "",
    double prior_corridor_progress_m = std::numeric_limits<double>::quiet_NaN())
  {
    GuardResult result;
    const bool contact_phase =
      task_config != nullptr && (phase == "terminal_contact" || phase == "drilling" ||
                                 phase == "retraction");
    const bool retraction_phase = task_config != nullptr && phase == "retraction";
    Eigen::Vector3d corridor_axis = Eigen::Vector3d::Zero();
    double corridor_length_m = 0.0;
    if (!std::isfinite(prior_corridor_progress_m))
    {
      prior_corridor_progress_m = last_corridor_progress_m_;
    }
    if (contact_phase)
    {
      const Eigen::Vector3d corridor =
        task_config->target_base_m - task_config->entry_base_m;
      corridor_length_m = corridor.norm();
      corridor_axis = corridor / corridor_length_m;
    }
    moveit::core::RobotState start(robot_model_);
    start.setToDefaultValues();
    start.setJointGroupPositions(joint_model_group_, start_positions);
    start.update();
    moveit::core::RobotState target(start);
    target.setJointGroupPositions(joint_model_group_, target_positions);
    target.update();

    if (!target.satisfiesBounds(joint_model_group_))
    {
      result.reason = "Requested state violates the URDF joint bounds.";
      return result;
    }

    const std::size_t sample_count = interpolation_sample_count(
      start_positions, target_positions);
    if (sample_count > static_cast<std::size_t>(maximum_interpolation_samples_))
    {
      result.reason = "Requested move exceeds the bounded interpolation budget.";
      return result;
    }

    planning_scene_monitor::LockedPlanningSceneRO scene(planning_scene_monitor_);
    result.world_object_count = scene->getWorld()->size();
    for (const std::string& object_id : scene->getWorld()->getObjectIds())
    {
      const collision_detection::World::ObjectConstPtr object =
        scene->getWorld()->getObject(object_id);
      if (!object)
      {
        continue;
      }
      WorldObjectEvidence evidence;
      evidence.id = object_id;
      evidence.shape_count = object->shapes_.size();
      const Eigen::Quaterniond object_orientation(object->pose_.linear());
      evidence.pose_xyzw = {
        object->pose_.translation().x(), object->pose_.translation().y(),
        object->pose_.translation().z(), object_orientation.x(),
        object_orientation.y(), object_orientation.z(), object_orientation.w()
      };
      for (std::size_t shape_index = 0;
           shape_index < object->shapes_.size() &&
           shape_index < object->global_shape_poses_.size();
           ++shape_index)
      {
        const shapes::ShapeConstPtr& shape = object->shapes_[shape_index];
        if (!shape || shape->type != shapes::MESH)
        {
          continue;
        }
        const auto* mesh = static_cast<const shapes::Mesh*>(shape.get());
        const Eigen::Isometry3d& shape_pose = object->global_shape_poses_[shape_index];
        for (unsigned int vertex_index = 0;
             vertex_index < mesh->vertex_count; ++vertex_index)
        {
          const Eigen::Vector3d local(
            mesh->vertices[3 * vertex_index],
            mesh->vertices[3 * vertex_index + 1],
            mesh->vertices[3 * vertex_index + 2]);
          const Eigen::Vector3d world = shape_pose * local;
          evidence.bounds_m[0] = std::min(evidence.bounds_m[0], world.x());
          evidence.bounds_m[1] = std::max(evidence.bounds_m[1], world.x());
          evidence.bounds_m[2] = std::min(evidence.bounds_m[2], world.y());
          evidence.bounds_m[3] = std::max(evidence.bounds_m[3], world.y());
          evidence.bounds_m[4] = std::min(evidence.bounds_m[4], world.z());
          evidence.bounds_m[5] = std::max(evidence.bounds_m[5], world.z());
          evidence.has_mesh_bounds = true;
        }
      }
      result.world_objects.push_back(std::move(evidence));
    }
    if (contact_phase && !scene->getWorld()->hasObject(task_config->target_object_id))
    {
      result.reason = "The configured selected target-tooth collision object is missing.";
      return result;
    }
    if (task_config != nullptr)
    {
      for (const std::string& object_id : task_config->clearance_exempt_object_ids)
      {
        if (!scene->getWorld()->hasObject(object_id))
        {
          result.reason = "A configured task-proximity collision object is missing.";
          result.second_body = object_id;
          return result;
        }
      }
      for (const std::string& object_id : task_config->simulation_guide_clearance_object_ids)
      {
        if (!scene->getWorld()->hasObject(object_id))
        {
          result.reason =
            "A configured simulation guide-clearance collision object is missing.";
          result.second_body = object_id;
          return result;
        }
      }
    }
    const auto& allowed_collision_matrix = scene->getAllowedCollisionMatrix();
    collision_detection::AllowedCollisionMatrix clearance_collision_matrix(
      allowed_collision_matrix);
    if (task_config != nullptr)
    {
      for (const std::string& object_id : task_config->clearance_exempt_object_ids)
      {
        // Every phased state omits only the explicitly configured burr-to-task
        // object pair from the research clearance-distance query. Production
        // publishes the selected target only; adjacent anatomy and guides are
        // not clearance exemptions. Collision remains strict during approach.
        // Terminal-contact and drilling additionally use phase_collision_matrix
        // below to suppress that same selected-target pair for exploratory
        // simulation.
        clearance_collision_matrix.setEntry(
          task_config->allowed_robot_link, object_id, true);
      }
    }
    if (contact_phase)
    {
      clearance_collision_matrix.setEntry(
        task_config->allowed_robot_link, task_config->target_object_id, true);
    }
    // Only the explicitly configured selected-target pair may omit the
    // research *distance* test. Ordinary/manual commands remain globally
    // strict; collision queries below always use the original ACM.
    const auto& clearance_acm =
      task_config != nullptr ? clearance_collision_matrix : allowed_collision_matrix;
    const auto& collision_environment = scene->getCollisionEnvUnpadded();
    moveit::core::RobotState sample(start);

    for (std::size_t index = 1; index <= sample_count; ++index)
    {
      const double interpolation = static_cast<double>(index) /
                                   static_cast<double>(sample_count);
      start.interpolate(target, interpolation, sample, joint_model_group_);
      sample.update();
      result.checked_samples = index;

      if (!sample.satisfiesBounds(joint_model_group_))
      {
        result.reason = "An interpolated state violates the URDF joint bounds.";
        return result;
      }

      collision_detection::CollisionRequest collision_request;
      collision_request.group_name = group_name_;
      collision_request.contacts = true;
      collision_request.max_contacts = 100;
      collision_request.max_contacts_per_pair = 20;
      collision_request.pad_environment_collisions = false;
      collision_request.pad_self_collisions = false;
      collision_detection::CollisionResult collision_result;
      scene->checkCollision(
        collision_request, collision_result, sample, allowed_collision_matrix);
      std::vector<std::pair<std::string, std::string>> admitted_housing_pairs;
      bool sample_housing_contact_warning = false;
      if (collision_result.collision)
      {
        if (!contact_phase)
        {
          result.reason = "MoveIt detected collision at interpolated sample " +
                          std::to_string(index) + "/" + std::to_string(sample_count) + ".";
          if (!collision_result.contacts.empty())
          {
            result.first_body = collision_result.contacts.begin()->first.first;
            result.second_body = collision_result.contacts.begin()->first.second;
          }
          return result;
        }
        // Suppress only the configured burr-target pair and exact
        // pneumatic_spindle-Copy-to-guide contacts after classifying every
        // reported contact. The complete predicate is then rerun with only
        // those exact pairs allowed so a second collision cannot be hidden.
        collision_detection::AllowedCollisionMatrix phase_collision_matrix(
          allowed_collision_matrix);
        phase_collision_matrix.setEntry(
          task_config->allowed_robot_link, task_config->target_object_id, true);
        const auto is_configured_guide = [task_config](const std::string& value) {
          return std::find(
                   task_config->simulation_guide_clearance_object_ids.begin(),
                   task_config->simulation_guide_clearance_object_ids.end(), value) !=
                 task_config->simulation_guide_clearance_object_ids.end();
        };
        const auto is_burr_target_pair = [task_config](
                                           const std::string& first,
                                           const std::string& second) {
          return (first == task_config->allowed_robot_link &&
                  second == task_config->target_object_id) ||
                 (second == task_config->allowed_robot_link &&
                  first == task_config->target_object_id);
        };
        const auto housing_guide_pair = [&is_configured_guide](
                                          const std::string& first,
                                          const std::string& second) {
          if (first == "pneumatic_spindle-Copy" && is_configured_guide(second))
          {
            return std::make_pair(first, second);
          }
          if (second == "pneumatic_spindle-Copy" && is_configured_guide(first))
          {
            return std::make_pair(second, first);
          }
          return std::make_pair(std::string(), std::string());
        };
        for (const auto& contact_entry : collision_result.contacts)
        {
          const std::string& first = contact_entry.first.first;
          const std::string& second = contact_entry.first.second;
          const bool burr_target = is_burr_target_pair(first, second);
          const auto housing_pair = housing_guide_pair(first, second);
          const bool housing_guide = !housing_pair.first.empty();
          if (!burr_target && !housing_guide)
          {
            result.reason =
              "MoveIt detected a non-approved collision at interpolated sample " +
              std::to_string(index) + "/" + std::to_string(sample_count) + ".";
            result.first_body = first;
            result.second_body = second;
            return result;
          }
          if (burr_target)
          {
            result.exploratory_tool_contact_suppressed = true;
          }
          if (!housing_guide)
          {
            continue;
          }
          bool has_finite_position = false;
          for (const auto& contact : contact_entry.second)
          {
            if (!std::isfinite(contact.depth))
            {
              result.reason =
                "Configured pneumatic_spindle-Copy guide contact has non-finite depth evidence.";
              result.first_body = first;
              result.second_body = second;
              return result;
            }
            if (!std::isfinite(contact.pos[0]) || !std::isfinite(contact.pos[1]) ||
                !std::isfinite(contact.pos[2]))
            {
              result.reason =
                "Configured pneumatic_spindle-Copy guide contact has no finite position evidence.";
              result.first_body = first;
              result.second_body = second;
              return result;
            }
            if (!has_finite_position)
            {
              for (std::size_t coordinate = 0; coordinate < 3; ++coordinate)
              {
                result.guide_clearance_warning_contact_position_base_m[coordinate] =
                  contact.pos[coordinate];
              }
              result.guide_clearance_warning_contact_position_available = true;
              has_finite_position = true;
            }
          }
          if (!has_finite_position)
          {
            result.reason =
              "Configured pneumatic_spindle-Copy guide contact had no finite contact evidence.";
            result.first_body = first;
            result.second_body = second;
            return result;
          }

          // FCL contact.depth is not reliable for every mesh/primitive pair.
          // Isolate this exact robot-guide pair and use the signed distance as
          // the authoritative penetration measurement.
          collision_detection::AllowedCollisionMatrix pair_distance_acm(
            allowed_collision_matrix);
          pair_distance_acm.setEntry(
            robot_model_->getLinkModelNames(), scene->getWorld()->getObjectIds(), true);
          pair_distance_acm.setEntry(housing_pair.first, housing_pair.second, false);
          collision_detection::DistanceRequest pair_distance_request;
          pair_distance_request.acm = &pair_distance_acm;
          pair_distance_request.enable_nearest_points = true;
          pair_distance_request.enable_signed_distance = true;
          pair_distance_request.distance_threshold = minimum_clearance_m_;
          collision_detection::DistanceResult pair_distance_result;
          collision_environment->distanceRobot(
            pair_distance_request, pair_distance_result, sample);
          const double signed_pair_distance_m =
            pair_distance_result.minimum_distance.distance;
          const auto measured_pair = std::make_pair(
            pair_distance_result.minimum_distance.link_names[0],
            pair_distance_result.minimum_distance.link_names[1]);
          const bool measured_exact_pair =
            (measured_pair.first == housing_pair.first &&
             measured_pair.second == housing_pair.second) ||
            (measured_pair.second == housing_pair.first &&
             measured_pair.first == housing_pair.second);
          if (!std::isfinite(signed_pair_distance_m) || !measured_exact_pair)
          {
            result.reason =
              "Configured pneumatic_spindle-Copy guide contact could not be isolated "
              "for signed penetration measurement (distance " +
              distance_mm_text(signed_pair_distance_m) + " mm, pair " +
              measured_pair.first + " / " + measured_pair.second + ").";
            result.first_body = first;
            result.second_body = second;
            return result;
          }
          const double maximum_penetration_m =
            std::abs(signed_pair_distance_m);
          if (maximum_penetration_m > SIMULATION_GUIDE_CONTACT_MAX_PENETRATION_M +
              CLEARANCE_COMPARISON_EPSILON_M)
          {
            result.guide_clearance_warning_contact_penetration_m = maximum_penetration_m;
            result.guide_clearance_warning_robot_link = housing_pair.first;
            result.guide_clearance_warning_object_id = housing_pair.second;
            result.reason =
              "Configured pneumatic_spindle-Copy guide contact penetration is " +
              distance_mm_text(maximum_penetration_m) +
              " mm; the simulation contact limit is 0.500000 mm.";
            result.first_body = first;
            result.second_body = second;
            return result;
          }
          phase_collision_matrix.setEntry(housing_pair.first, housing_pair.second, true);
          if (std::find(admitted_housing_pairs.begin(), admitted_housing_pairs.end(),
                        housing_pair) == admitted_housing_pairs.end())
          {
            admitted_housing_pairs.push_back(housing_pair);
          }
          sample_housing_contact_warning = true;
          if (!std::isfinite(result.guide_clearance_warning_contact_penetration_m) ||
              maximum_penetration_m > result.guide_clearance_warning_contact_penetration_m)
          {
            result.guide_clearance_warning_contact_penetration_m = maximum_penetration_m;
          }
          result.guide_clearance_warning_robot_link = housing_pair.first;
          result.guide_clearance_warning_object_id = housing_pair.second;
          // Keep the legacy minimum-warning field non-negative for old
          // consumers; the signed contact evidence is carried explicitly by
          // the contact penetration field below.
          result.minimum_guide_clearance_warning_m =
            result.guide_clearance_warning_contact_penetration_m;
        }
        if (collision_result.contacts.empty())
        {
          result.reason = "MoveIt reported a collision without contact evidence.";
          return result;
        }
        collision_detection::CollisionRequest phase_request;
        phase_request.group_name = group_name_;
        phase_request.contacts = true;
        phase_request.max_contacts = 100;
        phase_request.max_contacts_per_pair = 20;
        phase_request.pad_environment_collisions = false;
        phase_request.pad_self_collisions = false;
        collision_detection::CollisionResult phase_result;
        scene->checkCollision(
          phase_request, phase_result, sample, phase_collision_matrix);
        if (phase_result.collision)
        {
          result.reason =
            "MoveIt detected a non-tool or unconfigured collision at interpolated sample " +
            std::to_string(index) + "/" + std::to_string(sample_count) + ".";
          if (!phase_result.contacts.empty())
          {
            result.first_body = phase_result.contacts.begin()->first.first;
            result.second_body = phase_result.contacts.begin()->first.second;
            const auto& contacts = phase_result.contacts.begin()->second;
            if (!contacts.empty())
            {
              const auto& contact = contacts.front();
              result.minimum_world_distance_m = -contact.depth;
              for (std::size_t coordinate = 0; coordinate < 3; ++coordinate)
              {
                result.nearest_point_first_base_m[coordinate] = contact.pos[coordinate];
                result.nearest_point_second_base_m[coordinate] = contact.pos[coordinate];
              }
              result.nearest_points_available = true;
            }
          }
          return result;
        }
        if (result.exploratory_tool_contact_suppressed)
        {
          ++result.suppressed_tool_contact_sample_count;
        }
        if (sample_housing_contact_warning)
        {
          result.guide_clearance_warning = true;
          result.guide_warning_kind = "contact";
          ++result.guide_clearance_warning_sample_count;
          ++result.guide_clearance_warning_contact_sample_count;
        }
        if (!collision_result.contacts.empty())
        {
          result.first_body = collision_result.contacts.begin()->first.first;
          result.second_body = collision_result.contacts.begin()->first.second;
        }
      }

      collision_detection::DistanceRequest self_request;
      self_request.group_name = group_name_;
      self_request.acm = &clearance_acm;
      self_request.enable_nearest_points = true;
      self_request.enable_signed_distance = true;
      self_request.distance_threshold = minimum_clearance_m_;
      self_request.enableGroup(robot_model_);
      collision_detection::DistanceResult self_result;
      collision_environment->distanceSelf(self_request, self_result, sample);
      result.minimum_self_distance_m = std::min(
        result.minimum_self_distance_m, self_result.minimum_distance.distance);
      if (self_result.minimum_distance.distance <
          minimum_clearance_m_ - CLEARANCE_COMPARISON_EPSILON_M)
      {
        result.first_body = self_result.minimum_distance.link_names[0];
        result.second_body = self_result.minimum_distance.link_names[1];
        for (std::size_t coordinate = 0; coordinate < 3; ++coordinate)
        {
          result.nearest_point_first_base_m[coordinate] =
            self_result.minimum_distance.nearest_points[0][coordinate];
          result.nearest_point_second_base_m[coordinate] =
            self_result.minimum_distance.nearest_points[1][coordinate];
        }
        result.nearest_points_available = true;
        result.reason = "Self-clearance is " +
                        distance_mm_text(self_result.minimum_distance.distance) +
                        " mm; required minimum clearance is " +
                        distance_mm_text(minimum_clearance_m_) + " mm.";
        return result;
      }

      if (result.world_object_count > 0)
      {
        // Keep the reported minimum as the actual scene minimum.  Policy ACMs
        // below may omit the selected burr-target contact or a warned guide
        // pair, but those omissions must never rewrite the evidence field.
        collision_detection::DistanceRequest actual_world_request;
        actual_world_request.group_name = group_name_;
        actual_world_request.acm = &allowed_collision_matrix;
        actual_world_request.enable_nearest_points = true;
        actual_world_request.enable_signed_distance = true;
        actual_world_request.distance_threshold = minimum_clearance_m_;
        actual_world_request.enableGroup(robot_model_);
        collision_detection::DistanceResult actual_world_result;
        collision_environment->distanceRobot(
          actual_world_request, actual_world_result, sample);
        result.minimum_world_distance_m = std::min(
          result.minimum_world_distance_m, actual_world_result.minimum_distance.distance);

        // Start with the normal task clearance ACM.  A configured burr-guide
        // pair keeps its historical 0.1 mm requirement.  A configured guide
        // pair involving any other robot link may pass with a warning when
        // the distance is positive but below the 1 mm research margin.  Each
        // exact pair is then omitted and the bounded re-query looks for an
        // unrelated offending pair before accepting the sample.
        collision_detection::AllowedCollisionMatrix world_clearance_acm(
          clearance_acm);
        for (const auto& housing_pair : admitted_housing_pairs)
        {
          world_clearance_acm.setEntry(housing_pair.first, housing_pair.second, true);
        }
        const std::size_t guide_pair_limit = result.world_object_count *
          std::max<std::size_t>(1, robot_model_->getLinkModelNames().size());
        std::vector<std::pair<std::string, std::string>> skipped_guide_pairs;
        bool sample_guide_warning = false;
        collision_detection::DistanceRequest world_request;
        world_request.group_name = group_name_;
        world_request.enable_nearest_points = true;
        world_request.enable_signed_distance = true;
        world_request.distance_threshold = minimum_clearance_m_;
        world_request.enableGroup(robot_model_);
        for (;;)
        {
          world_request.acm = &world_clearance_acm;
          collision_detection::DistanceResult world_result;
          collision_environment->distanceRobot(world_request, world_result, sample);
          if (world_result.minimum_distance.distance >=
              minimum_clearance_m_ - CLEARANCE_COMPARISON_EPSILON_M)
          {
            break;
          }

          result.first_body = world_result.minimum_distance.link_names[0];
          result.second_body = world_result.minimum_distance.link_names[1];
          for (std::size_t coordinate = 0; coordinate < 3; ++coordinate)
          {
            result.nearest_point_first_base_m[coordinate] =
              world_result.minimum_distance.nearest_points[0][coordinate];
            result.nearest_point_second_base_m[coordinate] =
              world_result.minimum_distance.nearest_points[1][coordinate];
          }
          result.nearest_points_available = true;

          std::string guide_object_id;
          std::string guide_robot_link;
          if (task_config != nullptr)
          {
            const auto guide_pair = [this, &task_config](
                                      const std::string& first,
                                      const std::string& second) {
              const auto is_guide = [&task_config](const std::string& value) {
                return std::find(
                         task_config->simulation_guide_clearance_object_ids.begin(),
                         task_config->simulation_guide_clearance_object_ids.end(),
                         value) !=
                       task_config->simulation_guide_clearance_object_ids.end();
              };
              if (is_guide(first) && robot_model_->hasLinkModel(second))
              {
                return std::make_pair(first, second);
              }
              if (is_guide(second) && robot_model_->hasLinkModel(first))
              {
                return std::make_pair(second, first);
              }
              return std::make_pair(std::string(), std::string());
            }(result.first_body, result.second_body);
            guide_object_id = guide_pair.first;
            guide_robot_link = guide_pair.second;
          }
          if (!guide_object_id.empty())
          {
            const auto exact_pair = std::make_pair(guide_object_id, guide_robot_link);
            const double distance = world_result.minimum_distance.distance;
            if (distance <= CLEARANCE_COMPARISON_EPSILON_M)
            {
              result.reason = "Robot-to-world guide clearance is " +
                              distance_mm_text(distance) +
                              " mm; non-contact requires a positive distance.";
              return result;
            }
            const double guide_warning_threshold_m =
              guide_robot_link == "burr" ? SIMULATION_GUIDE_CLEARANCE_M :
                                             minimum_clearance_m_;
            if (distance < guide_warning_threshold_m)
            {
              result.guide_clearance_warning = true;
              if (result.guide_warning_kind.empty())
              {
                result.guide_warning_kind = "clearance";
              }
              sample_guide_warning = true;
              if (!std::isfinite(result.minimum_guide_clearance_warning_m) ||
                  distance < result.minimum_guide_clearance_warning_m)
              {
                result.minimum_guide_clearance_warning_m = distance;
                result.guide_clearance_warning_robot_link = guide_robot_link;
                result.guide_clearance_warning_object_id = guide_object_id;
              }
            }

            if (std::find(skipped_guide_pairs.begin(), skipped_guide_pairs.end(), exact_pair) !=
                skipped_guide_pairs.end())
            {
              result.reason =
                "Robot-to-world guide clearance could not be isolated safely; "
                "the exact configured guide pair remained the nearest offending pair.";
              return result;
            }
            if (skipped_guide_pairs.size() >= guide_pair_limit)
            {
              result.reason =
                "Robot-to-world guide clearance could not be isolated safely; "
                "the bounded configured guide-pair re-query was exhausted.";
              return result;
            }
            world_clearance_acm.setEntry(guide_robot_link, guide_object_id, true);
            skipped_guide_pairs.push_back(exact_pair);
            continue;
          }

          const double distance = world_result.minimum_distance.distance;
          if (distance > CLEARANCE_COMPARISON_EPSILON_M)
          {
            const bool first_is_robot = robot_model_->hasLinkModel(result.first_body);
            const bool second_is_robot = robot_model_->hasLinkModel(result.second_body);
            if (first_is_robot == second_is_robot)
            {
              result.reason =
                "Robot-to-world clearance warning pair could not be classified safely.";
              return result;
            }
            const std::string warning_robot_link =
              first_is_robot ? result.first_body : result.second_body;
            const std::string warning_object_id =
              first_is_robot ? result.second_body : result.first_body;
            const auto exact_pair = std::make_pair(warning_object_id, warning_robot_link);
            result.guide_clearance_warning = true;
            if (result.guide_warning_kind.empty())
            {
              result.guide_warning_kind = "clearance";
            }
            sample_guide_warning = true;
            if (!std::isfinite(result.minimum_guide_clearance_warning_m) ||
                distance < result.minimum_guide_clearance_warning_m)
            {
              result.minimum_guide_clearance_warning_m = distance;
              result.guide_clearance_warning_robot_link = warning_robot_link;
              result.guide_clearance_warning_object_id = warning_object_id;
            }
            if (std::find(skipped_guide_pairs.begin(), skipped_guide_pairs.end(), exact_pair) !=
                skipped_guide_pairs.end() || skipped_guide_pairs.size() >= guide_pair_limit)
            {
              result.reason =
                "Robot-to-world clearance warning pairs could not be isolated safely.";
              return result;
            }
            world_clearance_acm.setEntry(warning_robot_link, warning_object_id, true);
            skipped_guide_pairs.push_back(exact_pair);
            continue;
          }

          result.reason = "Robot-to-world clearance is " +
                          distance_mm_text(world_result.minimum_distance.distance) +
                          " mm; required minimum clearance is " +
                          distance_mm_text(minimum_clearance_m_) + " mm.";
          return result;
        }
        if (sample_guide_warning)
        {
          ++result.guide_clearance_warning_sample_count;
        }
      }

      if (contact_phase)
      {
        const Eigen::Vector3d tcp_base_m =
          sample.getGlobalLinkTransform(task_config->tool_tip_frame).translation();
        const Eigen::Vector3d from_entry = tcp_base_m - task_config->entry_base_m;
        const double progress_m = from_entry.dot(corridor_axis);
        const Eigen::Vector3d radial = from_entry - progress_m * corridor_axis;
        const double radial_distance_m = radial.norm();
        result.corridor_progress = progress_m;
        result.corridor_distance_m = radial_distance_m;
        if (radial_distance_m >
            task_config->corridor_radius_m + CORRIDOR_ENDPOINT_EPSILON_M)
        {
          result.reason = "The provisional drill tip left the approved Entry-to-Target corridor.";
          return result;
        }
        const double minimum_progress_m =
          phase == "drilling" ? 0.0 : -task_config->approach_standoff_m;
        const double maximum_progress_m =
          phase == "terminal_contact" ? 0.0 : corridor_length_m;
        if (progress_m < minimum_progress_m - CORRIDOR_ENDPOINT_EPSILON_M ||
            progress_m > maximum_progress_m + CORRIDOR_ENDPOINT_EPSILON_M)
        {
          result.reason = phase == "drilling" ?
            "The provisional drill tip overshot or preceded the approved drilling corridor." :
            "The terminal approach moved outside the pre-entry-to-Entry corridor.";
          return result;
        }
        if (!retraction_phase &&
            progress_m + CORRIDOR_MONOTONIC_EPSILON_M < prior_corridor_progress_m)
        {
          result.reason =
            "The provisional drill tip moved backwards along the approved corridor "
            "(current " + distance_mm_text(progress_m) + " mm, prior " +
            distance_mm_text(prior_corridor_progress_m) + " mm).";
          return result;
        }
        if (retraction_phase &&
            progress_m > prior_corridor_progress_m + CORRIDOR_MONOTONIC_EPSILON_M)
        {
          result.reason =
            "The provisional drill tip moved inward during guarded retraction "
            "along the approved corridor.";
          return result;
        }
        prior_corridor_progress_m = progress_m;
        result.corridor_ok = true;
      }
    }

    result.accepted = true;
    if (result.guide_clearance_warning)
    {
      if (result.guide_warning_kind == "contact")
      {
        result.reason =
          "Accepted with warning: non-rotating pneumatic_spindle-Copy contact with "
          "configured simulation guide " + result.guide_clearance_warning_object_id +
          " has " + distance_mm_text(result.guide_clearance_warning_contact_penetration_m) +
          " mm penetration; configured simulation contact limit is 0.500000 mm. "
          "Actual collision, self-clearance, unrelated clearance, and corridor checks passed.";
      }
      else
      {
        const bool burr_warning =
          result.guide_clearance_warning_robot_link == "burr";
        const bool configured_guide_warning = task_config != nullptr &&
          std::find(task_config->simulation_guide_clearance_object_ids.begin(),
                    task_config->simulation_guide_clearance_object_ids.end(),
                    result.guide_clearance_warning_object_id) !=
            task_config->simulation_guide_clearance_object_ids.end();
        result.reason = "Accepted with warning: robot link " +
                        result.guide_clearance_warning_robot_link + " is " +
                        distance_mm_text(result.minimum_guide_clearance_warning_m) +
                        " mm from " +
                        (configured_guide_warning ? "configured simulation guide " :
                                                    "world object ") +
                        result.guide_clearance_warning_object_id +
                        "; preferred clearance is " +
                        distance_mm_text(
                          burr_warning ? SIMULATION_GUIDE_CLEARANCE_M :
                                         minimum_clearance_m_) +
                        " mm. Positive separation, actual collision, self-clearance, "
                        "unrelated clearance, and corridor checks passed.";
      }
      if (result.exploratory_tool_contact_suppressed)
      {
        result.reason += " Configured burr-to-task contact was also suppressed for exploratory simulation.";
      }
    }
    else if (result.exploratory_tool_contact_suppressed)
    {
      result.reason =
        "Accepted for exploratory simulation only: configured burr-to-task-object "
        "contact was suppressed; bounds, non-tool collision, research clearance, "
        "and corridor checks passed. This is not a collision-safe result.";
    }
    else
    {
      result.reason = contact_phase ?
        "Accepted by the simulation phase guard: bounds, non-tool collision, research clearance, and corridor checks passed." :
        "Accepted: bounds, interpolated collision, and research clearance checks passed.";
    }
    return result;
  }

  std::size_t interpolation_sample_count(
    const std::vector<double>& start_positions,
    const std::vector<double>& target_positions) const
  {
    std::size_t samples = 1;
    for (std::size_t index = 0; index < joint_names_.size(); ++index)
    {
      const moveit::core::JointModel* joint = robot_model_->getJointOfVariable(joint_names_[index]);
      const double maximum_step =
        joint != nullptr && joint->getType() == moveit::core::JointModel::PRISMATIC ?
          maximum_prismatic_step_m_ : maximum_revolute_step_rad_;
      const double delta = std::abs(target_positions[index] - start_positions[index]);
      samples = std::max(samples, static_cast<std::size_t>(std::ceil(delta / maximum_step)));
    }
    return samples;
  }

  std::string distance_mm_text(double distance_m) const
  {
    if (!std::isfinite(distance_m))
    {
      return "unknown";
    }
    std::ostringstream output;
    output << std::fixed << std::setprecision(6) << distance_m * 1000.0;
    return output.str();
  }

  std::string world_objects_json(
    const std::vector<WorldObjectEvidence>& objects) const
  {
    std::ostringstream output;
    output << '[';
    for (std::size_t index = 0; index < objects.size(); ++index)
    {
      if (index > 0)
      {
        output << ',';
      }
      const WorldObjectEvidence& object = objects[index];
      output << '{'
             << "\"id\":\"" << json_escape(object.id) << "\","
             << "\"shape_count\":" << object.shape_count << ','
             << "\"pose_base_link_m_xyzw\":[";
      for (std::size_t pose_index = 0; pose_index < object.pose_xyzw.size(); ++pose_index)
      {
        if (pose_index > 0)
        {
          output << ',';
        }
        output << json_number(object.pose_xyzw[pose_index]);
      }
      output << "],\"bounds_base_link_m\":";
      if (!object.has_mesh_bounds)
      {
        output << "null";
      }
      else
      {
        output << '[';
        for (std::size_t bound_index = 0; bound_index < object.bounds_m.size(); ++bound_index)
        {
          if (bound_index > 0)
          {
            output << ',';
          }
          output << json_number(object.bounds_m[bound_index]);
        }
        output << ']';
      }
      output << '}';
    }
    output << ']';
    return output.str();
  }

  std::string status_json(
    const GuardResult& result,
    const std::vector<double>& requested,
    const std::vector<double>& accepted) const
  {
    std::ostringstream output;
    output << '{'
           << "\"schema\":\"" << STATUS_SCHEMA << "\","
           << "\"mode\":\"simulation_only\","
           << "\"accepted\":" << (result.accepted ? "true" : "false") << ','
           << "\"reason\":\"" << json_escape(result.reason) << "\","
           << "\"requested_positions\":" << json_array(requested) << ','
           << "\"accepted_positions\":" << json_array(accepted) << ','
           << "\"checked_samples\":" << result.checked_samples << ','
           << "\"minimum_clearance_m\":" << json_number(minimum_clearance_m_) << ','
           << "\"guide_clearance_warning\":"
           << (result.guide_clearance_warning ? "true" : "false") << ','
           << "\"guide_clearance_warning_sample_count\":"
           << result.guide_clearance_warning_sample_count << ','
           << "\"minimum_guide_clearance_warning_m\":"
           << json_number(result.minimum_guide_clearance_warning_m) << ','
           << "\"guide_clearance_warning_robot_link\":\""
           << json_escape(result.guide_clearance_warning_robot_link) << "\","
           << "\"guide_clearance_warning_object_id\":\""
           << json_escape(result.guide_clearance_warning_object_id) << "\","
           << "\"guide_warning_kind\":\""
           << json_escape(result.guide_warning_kind) << "\","
           << "\"guide_clearance_warning_contact_penetration_m\":"
           << json_number(result.guide_clearance_warning_contact_penetration_m) << ','
           << "\"guide_clearance_warning_contact_sample_count\":"
           << result.guide_clearance_warning_contact_sample_count << ','
           << "\"guide_clearance_warning_contact_position_base_m\":"
           << json_point_or_null(
                result.guide_clearance_warning_contact_position_base_m,
                result.guide_clearance_warning_contact_position_available) << ','
           << "\"minimum_self_distance_m\":"
           << json_number(result.minimum_self_distance_m) << ','
           << "\"minimum_world_distance_m\":"
           << json_number(result.minimum_world_distance_m) << ','
           << "\"first_body\":\"" << json_escape(result.first_body) << "\","
           << "\"second_body\":\"" << json_escape(result.second_body) << "\","
           << "\"nearest_point_first_base_m\":"
           << json_point_or_null(
                result.nearest_point_first_base_m, result.nearest_points_available) << ','
           << "\"nearest_point_second_base_m\":"
           << json_point_or_null(
                result.nearest_point_second_base_m, result.nearest_points_available) << ','
           << "\"world_object_count\":" << result.world_object_count << ','
           << "\"world_objects\":" << world_objects_json(result.world_objects)
           << '}';
    return output.str();
  }

  void publish_task_status(
    const GuardResult& result, const TaskJointCommand& command)
  {
    std::ostringstream output;
    output << '{'
           << "\"schema\":\"" << TASK_STATUS_SCHEMA << "\","
           << "\"mode\":\"simulation_only\","
           << "\"accepted\":" << (result.accepted ? "true" : "false") << ','
           << "\"reason\":\"" << json_escape(result.reason) << "\","
           << "\"task_fingerprint\":\""
           << json_escape(command.task_fingerprint) << "\","
           << "\"guard_session_id\":\""
           << json_escape(command.guard_session_id) << "\","
           << "\"phase\":\"" << json_escape(command.phase) << "\","
           << "\"sequence\":" << command.sequence << ','
           << "\"validate_only\":" << (command.validate_only ? "true" : "false") << ','
           << "\"requested_positions\":"
           << json_array(command.joint_positions) << ','
           << "\"accepted_positions\":"
           << json_array(last_accepted_positions_) << ','
           << "\"checked_samples\":" << result.checked_samples << ','
           << "\"corridor_ok\":" << (result.corridor_ok ? "true" : "false") << ','
           << "\"corridor_progress\":"
           << json_number(result.corridor_progress) << ','
           << "\"corridor_distance_m\":"
           << json_number(result.corridor_distance_m) << ','
           << "\"exploratory_tool_contact_suppressed\":"
           << (result.exploratory_tool_contact_suppressed ? "true" : "false") << ','
           << "\"suppressed_tool_contact_sample_count\":"
           << result.suppressed_tool_contact_sample_count << ','
           << "\"guide_clearance_warning\":"
           << (result.guide_clearance_warning ? "true" : "false") << ','
           << "\"guide_clearance_warning_sample_count\":"
           << result.guide_clearance_warning_sample_count << ','
           << "\"minimum_guide_clearance_warning_m\":"
           << json_number(result.minimum_guide_clearance_warning_m) << ','
           << "\"guide_clearance_warning_robot_link\":\""
           << json_escape(result.guide_clearance_warning_robot_link) << "\","
           << "\"guide_clearance_warning_object_id\":\""
           << json_escape(result.guide_clearance_warning_object_id) << "\","
           << "\"guide_warning_kind\":\""
           << json_escape(result.guide_warning_kind) << "\","
           << "\"guide_clearance_warning_contact_penetration_m\":"
           << json_number(result.guide_clearance_warning_contact_penetration_m) << ','
           << "\"guide_clearance_warning_contact_sample_count\":"
           << result.guide_clearance_warning_contact_sample_count << ','
           << "\"guide_clearance_warning_contact_position_base_m\":"
           << json_point_or_null(
                result.guide_clearance_warning_contact_position_base_m,
                result.guide_clearance_warning_contact_position_available) << ','
           << "\"minimum_clearance_m\":"
           << json_number(minimum_clearance_m_) << ','
           << "\"minimum_self_distance_m\":"
           << json_number(result.minimum_self_distance_m) << ','
           << "\"minimum_world_distance_m\":"
           << json_number(result.minimum_world_distance_m) << ','
           << "\"first_body\":\"" << json_escape(result.first_body) << "\","
           << "\"second_body\":\"" << json_escape(result.second_body) << "\","
           << "\"nearest_point_first_base_m\":"
           << json_point_or_null(
                result.nearest_point_first_base_m, result.nearest_points_available) << ','
           << "\"nearest_point_second_base_m\":"
           << json_point_or_null(
                result.nearest_point_second_base_m, result.nearest_points_available) << ','
           << "\"world_object_count\":" << result.world_object_count << ','
           << "\"world_objects\":" << world_objects_json(result.world_objects)
           << '}';
    std_msgs::msg::String message;
    message.data = output.str();
    task_status_publisher_->publish(message);
  }

  void publish_accepted(const std::vector<double>& values)
  {
    std_msgs::msg::Float64MultiArray message;
    message.data = values;
    accepted_publisher_->publish(message);
  }

  void publish_last_status()
  {
    // The validated-state consumer stores the most recent value, but it may
    // start or reconnect after the one-shot acceptance publish. Keep the
    // simulation state synchronized from the guard's existing heartbeat.
    publish_accepted(last_accepted_positions_);
    if (last_status_json_.empty())
    {
      return;
    }
    std_msgs::msg::String message;
    message.data = last_status_json_;
    status_publisher_->publish(message);
  }

  std::string group_name_;
  std::string raw_command_topic_;
  std::string accepted_command_topic_;
  std::string status_topic_;
  std::string task_config_topic_;
  std::string task_command_topic_;
  std::string task_status_topic_;
  double minimum_clearance_m_{ 0.001 };
  double maximum_revolute_step_rad_{ 0.017453292519943295 };
  double maximum_prismatic_step_m_{ 0.0005 };
  int maximum_interpolation_samples_{ 1000 };

  planning_scene_monitor::PlanningSceneMonitorPtr planning_scene_monitor_;
  moveit::core::RobotModelConstPtr robot_model_;
  const moveit::core::JointModelGroup* joint_model_group_{ nullptr };
  std::vector<std::string> joint_names_;
  std::vector<double> last_accepted_positions_;
  TaskGuardConfig task_config_;
  std::string active_task_config_payload_;
  std::int64_t last_task_sequence_{ -1 };
  double last_corridor_progress_m_{ 0.0 };
  std::vector<double> preflight_positions_;
  std::int64_t last_preflight_sequence_{ -1 };
  double last_preflight_corridor_progress_m_{ 0.0 };
  std::string last_status_json_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr accepted_publisher_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_publisher_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr task_status_publisher_;
  rclcpp::Subscription<std_msgs::msg::Float64MultiArray>::SharedPtr command_subscription_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr task_config_subscription_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr task_command_subscription_;
  rclcpp::TimerBase::SharedPtr heartbeat_timer_;
};

int main(int argc, char** argv)
{
  rclcpp::init(argc, argv);
  try
  {
    auto node = std::make_shared<DentobotCollisionGuard>();
    node->initialize();
    rclcpp::spin(node);
  }
  catch (const std::exception& exception)
  {
    RCLCPP_FATAL(rclcpp::get_logger("dentobot_collision_guard"), "%s", exception.what());
    rclcpp::shutdown();
    return 1;
  }
  rclcpp::shutdown();
  return 0;
}
