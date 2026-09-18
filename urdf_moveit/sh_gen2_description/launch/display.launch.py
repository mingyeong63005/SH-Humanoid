"""URDF를 RViz에 띄우는 launch 파일.

사용법:
  ros2 launch sh_gen2_description display.launch.py
  ros2 launch sh_gen2_description display.launch.py gui:=false
  ros2 launch sh_gen2_description display.launch.py model:=/절대경로/다른파일.urdf.xacro
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_share = FindPackageShare('sh_gen2_description')

    model_arg = DeclareLaunchArgument(
        'model',
        default_value=PathJoinSubstitution([pkg_share, 'urdf', 'sh_gen2.urdf.xacro']),
        description='URDF 또는 xacro 파일 경로')
    gui_arg = DeclareLaunchArgument(
        'gui', default_value='true',
        description='관절 슬라이더 창(joint_state_publisher_gui) 사용 여부')

    robot_description = ParameterValue(
        Command(['xacro ', LaunchConfiguration('model')]), value_type=str)

    return LaunchDescription([
        model_arg,
        gui_arg,
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            parameters=[{'robot_description': robot_description}]),
        Node(
            condition=IfCondition(LaunchConfiguration('gui')),
            package='joint_state_publisher_gui',
            executable='joint_state_publisher_gui'),
        Node(
            condition=UnlessCondition(LaunchConfiguration('gui')),
            package='joint_state_publisher',
            executable='joint_state_publisher'),
        Node(
            package='rviz2',
            executable='rviz2',
            arguments=['-d', PathJoinSubstitution([pkg_share, 'rviz', 'display.rviz'])],
            output='screen'),
    ])
