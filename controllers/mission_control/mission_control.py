"""main controller."""

import py_trees
import numpy as np

from controller import Robot, Supervisor

from py_trees.composites import Sequence, Parallel, Selector
from py_trees.behaviour import Behaviour
from py_trees.common import Status

from skill_bridge import ReportSkill, requested_skill
from near_hud import PrepareClaim, ShowSettlement, ShowMissionSummary, reset_mission_log

from arm_control import open_gripper, grab_item, arm_travel_position, arm_extend_position, lift_arm
from body_control import change_height_to, search
from travel_control import route, move, get_in_position, back_up, rotate_to_face
from mapping import test_for_map, map_environment


robot = Supervisor()
timestep = int(robot.getBasicTimeStep())
reset_mission_log()

#---------------------------------------------------

motors = {
    "arm_1_joint": robot.getDevice("arm_1_joint"),
    "arm_2_joint": robot.getDevice("arm_2_joint"),
    "arm_3_joint": robot.getDevice("arm_3_joint"),
    "arm_4_joint": robot.getDevice("arm_4_joint"),
    "arm_5_joint": robot.getDevice("arm_5_joint"),
    "arm_6_joint": robot.getDevice("arm_6_joint"),
    "arm_7_joint": robot.getDevice("arm_7_joint"),
    "torso_lift_joint": robot.getDevice("torso_lift_joint")
    # Add more as needed
}

JC = { 'openGripper' : {'gripper_left_finger_joint' : 0.045,
                        'gripper_right_finger_joint': 0.045},
       'closeGripper': {'gripper_left_finger_joint' : 0.0,
                        'gripper_right_finger_joint': 0.0}}
encoders = {
    "arm_1_joint": robot.getDevice("arm_1_joint_sensor"),
    "arm_2_joint": robot.getDevice("arm_2_joint_sensor"),
    "arm_3_joint": robot.getDevice("arm_3_joint_sensor"),
    "arm_4_joint": robot.getDevice("arm_4_joint_sensor"),
    "arm_5_joint": robot.getDevice("arm_5_joint_sensor"),
    "arm_6_joint": robot.getDevice("arm_6_joint_sensor"),
    "arm_7_joint": robot.getDevice("arm_7_joint_sensor"),
    "torso_lift_joint": robot.getDevice("torso_lift_joint_sensor"),
    "gripper_left_finger_joint": robot.getDevice("gripper_left_sensor_finger_joint"),
    "gripper_right_finger_joint": robot.getDevice("gripper_right_sensor_finger_joint")
}
#for encoder in encoders.values():    encoder.enable(timestep)

#---------------------------target for motors in arm----------
targets = {
    "arm_1_joint": 1.6,
    "arm_2_joint": 1,
    "arm_3_joint": 2,
    "arm_4_joint": 2,
    "arm_5_joint": 0,
    "arm_6_joint": 0,
    "arm_7_joint": 1.6,
    "torso_lift_joint": 0.28,
}

map_WP = [(0.3,0),(0.42,-.31),(0.45,-2.5),(-0.66,-3.2),(-1.5,-2.9),(-1.71,-1),(-1.36,0),(-0.3,0.4)]
camera_to_gripper = np.array([0.5,0,-0.25]) #distances
gps_to_camera = np.array([0.23,0,0.9457]) #distances
drop_zones = np.array([[-0.38,-0.68,0.75],[-0.55,-1.39,0.75],[-0.54,-2.17,0.75]])
drop_positions = [(189,100),(200,160),(195,229)]
grab_position = (170,75)
#---------------------Blackboard for data storage in BT-------

class BB:
    def __init__(self):
        self.data = {}
    def write(self,key,value):
        self.data[key] = value
    def read(self,key):
        return self.data.get(key)

blackboard = BB()
blackboard.write('robot',robot)
blackboard.write('motors_dict',motors)
blackboard.write('encoders_dict',encoders)
blackboard.write('targets_dict',targets)
blackboard.write('WP',map_WP)
blackboard.write('Grip',JC)
blackboard.write('GPSTC',gps_to_camera)
blackboard.write('CTG',camera_to_gripper)
blackboard.write('drop_zones',drop_zones)
blackboard.write('drop_positions',drop_positions)

class update(Behaviour):
    def __init__(self, name, blackboard, key1, key2, change):
        super(update, self).__init__(name)
        self.blackboard = blackboard
        self.key1 = key1
        self.key2 = key2
        self.change = change

    def initialise(self):
        pass

    def update(self):
        modify = self.blackboard.read(self.key1)
        if modify is not None:
            modify[self.key2] = self.change
            self.blackboard.write(self.key1, modify)
            return Status.SUCCESS
        else:
            print(f"Key '{self.key1}' not found in blackboard.")
            return Status.FAILURE

#--------------------------------------------------

#The Behaviour Tree (BT)------------------------------------------------------

prep = Sequence("prep", children=[
        arm_travel_position("get ready to move",blackboard),
        Selector("Does Map Exist?", children=[
            test_for_map("Test for map"),
            Parallel("Mapping",policy=py_trees.common.ParallelPolicy.SuccessOnOne(), children =[
                map_environment("Map the environment",blackboard),
                move("Move around the table",blackboard)
                ])],memory=True),
        ], memory=True)

def _honey_pick_nodes():
    return [
        route("compute path to counter", blackboard, grab_position),
        move("move to counter", blackboard),
        search("look for honey", blackboard, ["honey jar", "jam jar"]),
        change_height_to("adjust height", blackboard, object_name="honey jar"),
        rotate_to_face("honey jar", blackboard, object_name="honey jar"),
        arm_extend_position("arm grab ready", blackboard),
        open_gripper("open grip", blackboard),
        get_in_position("approach honey", blackboard, object_name="honey jar"),
        grab_item("grab honey jar", blackboard),
        lift_arm("pick up honey jar", blackboard),
        back_up("pull back", blackboard),
        back_up("pull back", blackboard),
    ]

def _jam_pick_nodes(tag):
    return [
        route("compute path to counter %s" % tag, blackboard, grab_position),
        move("move to counter %s" % tag, blackboard),
        change_height_to("adjust height %s" % tag, blackboard, object_name="jam jar"),
        arm_travel_position("get ready to move %s" % tag, blackboard),
        rotate_to_face(tag, blackboard, object_name="jam jar"),
        arm_extend_position("arm grab ready %s" % tag, blackboard),
        get_in_position("approach %s" % tag, blackboard, object_name="jam jar"),
        grab_item("grab %s" % tag, blackboard),
        lift_arm("pick up %s" % tag, blackboard),
        back_up("pull back %s a" % tag, blackboard),
        back_up("pull back %s b" % tag, blackboard),
    ]

def _place_nodes(zone, tag, extra=None):
    nodes = [
        route("compute path to zone %s" % tag, blackboard, drop_positions[zone]),
        move("move to drop zone %s" % tag, blackboard),
        rotate_to_face("spot %s" % tag, blackboard, zone=zone),
        get_in_position("approach spot %s" % tag, blackboard, zone=zone),
        arm_extend_position("arm place ready %s" % tag, blackboard),
        change_height_to("adjust height zone %s" % tag, blackboard, zone=zone),
        open_gripper("release %s" % tag, blackboard),
        back_up("pull back after %s" % tag, blackboard),
        lift_arm("move out of way %s" % tag, blackboard),
    ]
    if extra:
        nodes.extend(extra)
    return nodes

def _delivery(name, skill_id, motion_nodes):
    return Sequence(
        name,
        children=[
            Parallel(
                "fund while %s" % name,
                policy=py_trees.common.ParallelPolicy.SuccessOnAll(),
                children=[
                    PrepareClaim("prepare %s" % skill_id, blackboard, skill_id),
                    Sequence("motion %s" % name, children=motion_nodes, memory=True),
                ],
            ),
            ReportSkill("report %s" % skill_id, blackboard, skill_id),
            ShowSettlement("show NEAR %s" % skill_id, blackboard, skill_id),
        ],
        memory=True,
    )

fetch_honey = _delivery("fetch_honey", "fetch_honey", _honey_pick_nodes())
fetch_honey_deliver = _delivery(
    "fetch_honey_deliver",
    "fetch_honey",
    _honey_pick_nodes() + _place_nodes(0, "honey"),
)
place_zone_0 = Sequence(
    "place_zone_0",
    children=_place_nodes(0, "z0")
    + [
        ReportSkill("report place_zone_0", blackboard, "place_zone_0"),
        ShowSettlement("show NEAR place_zone_0", blackboard, "place_zone_0"),
    ],
    memory=True,
)
fetch_jam = _delivery("fetch_jam", "fetch_jam", _jam_pick_nodes("jam 1"))
place_zone_1 = Sequence(
    "place_zone_1",
    children=_place_nodes(1, "z1")
    + [
        ReportSkill("report place_zone_1", blackboard, "place_zone_1"),
        ShowSettlement("show NEAR place_zone_1", blackboard, "place_zone_1"),
    ],
    memory=True,
)
fetch_jam_deliver = _delivery(
    "fetch_jam_deliver",
    "fetch_jam",
    _jam_pick_nodes("jam 1") + _place_nodes(1, "jam"),
)
fetch_jam_2 = _delivery("fetch_jam_2", "fetch_jam_2", _jam_pick_nodes("jam 2"))
place_zone_2 = Sequence(
    "place_zone_2",
    children=_place_nodes(
        2,
        "z2",
        extra=[
            route("compute path to counter after z2", blackboard, grab_position),
            move("move to counter after z2", blackboard),
        ],
    )
    + [
        ReportSkill("report place_zone_2", blackboard, "place_zone_2"),
        ShowSettlement("show NEAR place_zone_2", blackboard, "place_zone_2"),
    ],
    memory=True,
)
fetch_jam_2_deliver = _delivery(
    "fetch_jam_2_deliver",
    "fetch_jam_2",
    _jam_pick_nodes("jam 2")
    + _place_nodes(
        2,
        "jam2",
        extra=[
            route("compute path to counter after jam2", blackboard, grab_position),
            move("move to counter after jam2", blackboard),
        ],
    ),
)

SKILLS = {
    "fetch_honey": fetch_honey,
    "fetch_honey_deliver": fetch_honey_deliver,
    "place_zone_0": place_zone_0,
    "fetch_jam": fetch_jam,
    "place_zone_1": place_zone_1,
    "fetch_jam_deliver": fetch_jam_deliver,
    "fetch_jam_2": fetch_jam_2,
    "place_zone_2": place_zone_2,
    "fetch_jam_2_deliver": fetch_jam_2_deliver,
}

ALL_MISSION = [
    prep,
    fetch_honey_deliver,
    fetch_jam_deliver,
    fetch_jam_2_deliver,
    ShowMissionSummary("mission txs", blackboard),
]

_skill = requested_skill()
print("HOTEL_SKILL", _skill)
if _skill == "all" or _skill not in SKILLS:
    _children = ALL_MISSION
else:
    _children = [prep, SKILLS[_skill]]

BT = Sequence("main", children=_children, memory=True)
BT.setup_with_descendants()
#-----------------------------------------------------------------------------

#RUN BT
while robot.step(timestep) != -1:
    BT.tick_once()
    if BT.status != py_trees.common.Status.RUNNING:
        print("DONE")
        break