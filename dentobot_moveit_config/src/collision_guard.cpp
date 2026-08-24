#include <algorithm>
#include <chrono>
#include <cmath>
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
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/float64_multi_array.hpp>
#include <std_msgs/msg/string.hpp>

namespace
{
constexpr char STATUS_SCHEMA[] = "dentobot.joint_command_status.v1";
constexpr double CLEARANCE_COMPARISON_EPSILON_M = 1e-9;

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
    minimum_clearance_m_ = declare_parameter<double>("minimum_clearance_m", 0.005);
    maximum_revolute_step_rad_ = declare_parameter<double>(
      "maximum_revolute_step_rad", 0.017453292519943295);
    maximum_prismatic_step_m_ = declare_parameter<double>(
      "maximum_prismatic_step_m", 0.0005);
    maximum_interpolation_samples_ = declare_parameter<int>(
      "maximum_interpolation_samples", 1000);

    if (group_name_.empty() || raw_command_topic_.empty() ||
        accepted_command_topic_.empty() || status_topic_.empty())
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
    command_subscription_ = create_subscription<std_msgs::msg::Float64MultiArray>(
      raw_command_topic_, 10,
      std::bind(&DentobotCollisionGuard::on_command, this, std::placeholders::_1));
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

  GuardResult validate_motion(
    const std::vector<double>& start_positions,
    const std::vector<double>& target_positions)
  {
    GuardResult result;
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
    const auto& allowed_collision_matrix = scene->getAllowedCollisionMatrix();
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
        result.reason = "MoveIt detected collision at interpolated sample " +
                        std::to_string(index) + "/" + std::to_string(sample_count) + ".";
        if (!collision_result.contacts.empty())
        {
          result.first_body = collision_result.contacts.begin()->first.first;
          result.second_body = collision_result.contacts.begin()->first.second;
        }
        return result;
      }

      collision_detection::DistanceRequest self_request;
      self_request.group_name = group_name_;
      self_request.acm = &allowed_collision_matrix;
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
        world_request.acm = &allowed_collision_matrix;
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
    }

    result.accepted = true;
    result.reason = "Accepted: bounds, interpolated collision, and 5 mm clearance checks passed.";
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
           << "\"world_object_count\":" << result.world_object_count
           << '}';
    return output.str();
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
  double minimum_clearance_m_{ 0.005 };
  double maximum_revolute_step_rad_{ 0.017453292519943295 };
  double maximum_prismatic_step_m_{ 0.0005 };
  int maximum_interpolation_samples_{ 1000 };

  planning_scene_monitor::PlanningSceneMonitorPtr planning_scene_monitor_;
  moveit::core::RobotModelConstPtr robot_model_;
  const moveit::core::JointModelGroup* joint_model_group_{ nullptr };
  std::vector<std::string> joint_names_;
  std::vector<double> last_accepted_positions_;
  std::string last_status_json_;
  rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr accepted_publisher_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_publisher_;
  rclcpp::Subscription<std_msgs::msg::Float64MultiArray>::SharedPtr command_subscription_;
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
