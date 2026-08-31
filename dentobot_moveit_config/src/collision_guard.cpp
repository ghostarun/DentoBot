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
constexpr char TASK_CONFIG_SCHEMA[] = "dentobot.task_guard_config.v2";
constexpr char TASK_COMMAND_SCHEMA[] = "dentobot.task_joint_command.v2";
constexpr char TASK_STATUS_SCHEMA[] = "dentobot.task_joint_status.v2";
constexpr double CLEARANCE_COMPARISON_EPSILON_M = 1e-9;
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
  std::size_t world_object_count{ 0 };
  std::vector<WorldObjectEvidence> world_objects;
  bool corridor_ok{ false };
  double corridor_progress{ std::numeric_limits<double>::quiet_NaN() };
  double corridor_distance_m{ std::numeric_limits<double>::quiet_NaN() };
  bool exploratory_tool_contact_suppressed{ false };
  std::size_t suppressed_tool_contact_sample_count{ 0 };
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
      result.reason = "Expected " + std::to_string(joint_names_.size()) +
                      " joint values, received " + std::to_string(requested.size()) + ".";
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
         command.phase != "drilling"))
    {
      reason = "Phased command identity, phase, or sequence is invalid.";
      return false;
    }
    if (command.joint_positions.size() != joint_names_.size() ||
        !std::all_of(command.joint_positions.begin(), command.joint_positions.end(),
                     [](double value) { return std::isfinite(value); }))
    {
      reason = "Phased command must contain six finite ordered joint values.";
      return false;
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
    else if (command.sequence <= last_task_sequence_)
    {
      result.reason = "Phased command sequence is stale or duplicated.";
    }
    else
    {
      result = validate_motion(
        last_accepted_positions_, command.joint_positions, &task_config_, command.phase);
    }

    if (result.accepted)
    {
      last_accepted_positions_ = command.joint_positions;
      last_task_sequence_ = command.sequence;
      if (command.phase == "terminal_contact" || command.phase == "drilling")
      {
        last_corridor_progress_m_ = result.corridor_progress;
      }
      publish_accepted(last_accepted_positions_);
    }
    publish_task_status(result, command);
  }

  GuardResult validate_motion(
    const std::vector<double>& start_positions,
    const std::vector<double>& target_positions,
    const TaskGuardConfig* task_config = nullptr,
    const std::string& phase = "")
  {
    GuardResult result;
    const bool contact_phase =
      task_config != nullptr && (phase == "terminal_contact" || phase == "drilling");
    Eigen::Vector3d corridor_axis = Eigen::Vector3d::Zero();
    double corridor_length_m = 0.0;
    double prior_corridor_progress_m = last_corridor_progress_m_;
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
    }
    const auto& allowed_collision_matrix = scene->getAllowedCollisionMatrix();
    collision_detection::AllowedCollisionMatrix clearance_collision_matrix(
      allowed_collision_matrix);
    collision_detection::AllowedCollisionMatrix phase_collision_matrix(
      allowed_collision_matrix);
    if (task_config != nullptr)
    {
      for (const std::string& object_id : task_config->clearance_exempt_object_ids)
      {
        // Every phased state omits only the configured burr-to-task-object
        // pair from the research clearance-distance query. Collision remains
        // strict during approach. Terminal-contact and drilling additionally
        // use phase_collision_matrix below to suppress that same tool-only
        // pair for exploratory simulation.
        clearance_collision_matrix.setEntry(
          task_config->allowed_robot_link, object_id, true);
        if (contact_phase)
        {
          phase_collision_matrix.setEntry(
            task_config->allowed_robot_link, object_id, true);
        }
      }
    }
    if (contact_phase)
    {
      clearance_collision_matrix.setEntry(
        task_config->allowed_robot_link, task_config->target_object_id, true);
      phase_collision_matrix.setEntry(
        task_config->allowed_robot_link, task_config->target_object_id, true);
    }
    // Every phased task state may place the burr near task anatomy or inside
    // the approved guide bore, including the collision-free approach to
    // pre-entry. Exempt only configured burr-to-object pairs from the research
    // *distance* test. Ordinary/manual commands remain globally strict;
    // collision queries below always use the original ACM.
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
      collision_request.max_contacts = 20;
      collision_request.max_contacts_per_pair = 1;
      collision_request.pad_environment_collisions = false;
      collision_request.pad_self_collisions = false;
      collision_detection::CollisionResult collision_result;
      scene->checkCollision(
        collision_request, collision_result, sample, allowed_collision_matrix);
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
        // The exploratory terminal/drilling policy suppresses only collisions
        // between the configured burr link and explicitly configured task
        // anatomy/guide objects. Re-run MoveIt's complete collision predicate
        // with those exact pairs allowed. This is safer than accepting based on
        // the truncated diagnostic contact list: any self collision, other
        // robot-link/world collision, or unconfigured world collision remains.
        collision_detection::CollisionRequest phase_request;
        phase_request.group_name = group_name_;
        phase_request.contacts = true;
        phase_request.max_contacts = 20;
        phase_request.max_contacts_per_pair = 1;
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
          }
          return result;
        }
        result.exploratory_tool_contact_suppressed = true;
        ++result.suppressed_tool_contact_sample_count;
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
        result.reason = "Self-clearance is " +
                        distance_mm_text(self_result.minimum_distance.distance) +
                        " mm; the draft minimum is " +
                        distance_mm_text(minimum_clearance_m_) + " mm.";
        return result;
      }

      if (result.world_object_count > 0)
      {
        collision_detection::DistanceRequest world_request;
        world_request.group_name = group_name_;
        world_request.acm = &clearance_acm;
        world_request.enable_nearest_points = true;
        world_request.enable_signed_distance = true;
        world_request.distance_threshold = minimum_clearance_m_;
        world_request.enableGroup(robot_model_);
        collision_detection::DistanceResult world_result;
        collision_environment->distanceRobot(world_request, world_result, sample);
        result.minimum_world_distance_m = std::min(
          result.minimum_world_distance_m, world_result.minimum_distance.distance);
        if (world_result.minimum_distance.distance <
            minimum_clearance_m_ - CLEARANCE_COMPARISON_EPSILON_M)
        {
          result.first_body = world_result.minimum_distance.link_names[0];
          result.second_body = world_result.minimum_distance.link_names[1];
          result.reason = "Robot-to-world clearance is " +
                          distance_mm_text(world_result.minimum_distance.distance) +
                          " mm; the draft minimum is " +
                          distance_mm_text(minimum_clearance_m_) + " mm.";
          return result;
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
          phase == "terminal_contact" ? -task_config->approach_standoff_m : 0.0;
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
        if (progress_m + CORRIDOR_MONOTONIC_EPSILON_M < prior_corridor_progress_m)
        {
          result.reason =
            "The provisional drill tip moved backwards along the approved corridor "
            "(current " + distance_mm_text(progress_m) + " mm, prior " +
            distance_mm_text(prior_corridor_progress_m) + " mm).";
          return result;
        }
        prior_corridor_progress_m = progress_m;
        result.corridor_ok = true;
      }
    }

    result.accepted = true;
    if (result.exploratory_tool_contact_suppressed)
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
           << "\"minimum_self_distance_m\":"
           << json_number(result.minimum_self_distance_m) << ','
           << "\"minimum_world_distance_m\":"
           << json_number(result.minimum_world_distance_m) << ','
           << "\"first_body\":\"" << json_escape(result.first_body) << "\","
           << "\"second_body\":\"" << json_escape(result.second_body) << "\","
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
           << "\"minimum_clearance_m\":"
           << json_number(minimum_clearance_m_) << ','
           << "\"minimum_self_distance_m\":"
           << json_number(result.minimum_self_distance_m) << ','
           << "\"minimum_world_distance_m\":"
           << json_number(result.minimum_world_distance_m) << ','
           << "\"first_body\":\"" << json_escape(result.first_body) << "\","
           << "\"second_body\":\"" << json_escape(result.second_body) << "\","
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
