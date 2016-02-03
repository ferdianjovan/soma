import rospy
import tf
import world_state
import zlib

from roslib import message

import xmltodict
import os
import python_pcd
from geometry_msgs.msg import PoseStamped, Pose, Point, Quaternion
from std_msgs.msg import Header
import genpy
import numpy as np
import sensor_msgs.point_cloud2 as pc2
import datetime

"""
read the G4S datasets load to
ws_observation collection()
and object collection(including room object and the objects got from segmentation)
"""

def get_number(s):
    """ return the number (int) in a string. uggly assumptions made """
    s = [c for c in s if c in "0123456789"]
    return "".join(s)

def parse_room(world, dirname, files, class_lookup):
    files.sort()
    if "room.xml" in files:
        with open(os.path.join(dirname, "room.xml"), "r") as f:
            room = xmltodict.parse(f)
        room_name = room['SemanticRoom']["RoomStringId"]

        #Creat room object in world_state if it is the first time to store
        """
        room object should contain all the observation in this room
        """
        if not world.does_object_exist(room_name):
            room_object = world.create_object(room_name)
        else:
            room_object = world.get_object(room_name)

        # Add the intermediate clouds as observations
        observations = {}
        for cloud_info in room['SemanticRoom']["RoomIntermediateClouds"]["RoomIntermediateCloud"]:
            print cloud_info["@filename"]
            print "Calculating cloud frame..."
            """
            read form xml get info about a point cloud
            transform: Ros Header, Pose are included
            transform_reg: Header, Pose are included
            """
            time_stamp = rospy.Time(int(cloud_info["RoomIntermediateCloudTransform"]['Stamp']['sec']),
                                    int(cloud_info["RoomIntermediateCloudTransform"]['Stamp']['nsec']))
            transform = cloud_info["RoomIntermediateCloudTransform"]
            transform = PoseStamped(Header(0,
                                           genpy.Time(int(transform['Stamp']['sec']),
                                                      int(transform['Stamp']['nsec'])),
                                           transform["FrameId"]),
                                    Pose(Point(float(transform['Transform']['Translation']['x']),
                                               float(transform['Transform']['Translation']['y']),
                                               float(transform['Transform']['Translation']['z'])),
                                         Quaternion(float(transform['Transform']['Rotation']['x']),
                                                    float(transform['Transform']['Rotation']['y']),
                                                    float(transform['Transform']['Rotation']['z']),
                                                    float(transform['Transform']['Rotation']['w']))))
            transform_reg = cloud_info["RoomIntermediateCloudTransformRegistered"]
            transform_reg = PoseStamped(Header(0,
                                               genpy.Time(int(transform_reg['@Stamp_sec']),
                                                          int(transform_reg['@Stamp_nsec'])),
                                               transform_reg["@FrameId"]),
                                        Pose(Point(float(transform_reg['@Trans_x']),
                                                   float(transform_reg['@Trans_y']),
                                                   float(transform_reg['@Trans_z'])),
                                             Quaternion(float(transform_reg['@Rot_x']),
                                                        float(transform_reg['@Rot_y']),
                                                        float(transform_reg['@Rot_z']),
                                                        float(transform_reg['@Rot_w']))))
            """
            pose are extracted form above generated two ros msg
            the final 'pose' is generated by multiplying original pose and transformation matrix
            """
            p1 = world_state.geometry.Pose.from_ros_msg(transform)
            p2 = world_state.geometry.Pose.from_ros_msg(transform_reg)
            pose = world_state.geometry.Pose.from_homog(np.dot(p2.as_homog_matrix(),
                                                               p1.as_homog_matrix()))
            print "ok."
            print "Reading cloud PCD..."

            """
            load point cloud from pcd file, the default get_tf is false.
            """
            cloud = python_pcd.io.read_pcd(os.path.join(dirname,
                                                        cloud_info['@filename']),
                                           get_tf=False)
            print "done."

            """
            generate a tf message 't'
            define a Header for point cloud data
            """
            t = pose.to_ros_tf()
            t.header.stamp.secs = time_stamp.secs
            t.header.stamp.nsecs = time_stamp.nsecs
            cloud.header.stamp.secs = time_stamp.secs
            cloud.header.stamp.nsecs = time_stamp.nsecs

            print "Creating observations..."
            transform_store = world_state.observation.TransformationStore.create_from_transforms([t])

            """
            Here tf and point cloud is stored in 'message_store' database,
            observation is stored in 'world_state', it contains the index_id of the above two data.
            e.g. in which database the topic is stored? which collection? what's the topic type? the identification?
            """
            #insert zlib pickled tf message and point cloud to database
            observation = world_state.observation.Observation.make_observation_from_messages(
                [("/tf", transform_store.pickle_to_msg()),
                 ("/head_xtion/depth_registered/points", cloud)])
            print "ok."

            observation.stamp = time_stamp.to_time()
            observations[get_number(cloud_info["@filename"])] = observation

            #add the new observation to this room_observation index in 'Object' collection
            print "Adding room observation to index..."
            room_object.add_observation(observation)
            print "ok"

        # What objects are "live" in this room at this point in time
        """
        live object should get from the tf, as we are load data from file 'live_object' is blank
        """
        live_objects = map(lambda x: x.name, world.get_children(room_name, {'_life_end': None,}))


        """
        find labeled object add it to 'Object' collection. If the object is the same
        object we added before, add info to sub-member '_observations' and '_poses'
        the data of a object contains
        """
        # What objects are labeled in this room
        for fl in files:
            f = fl.split("_")
            if len(f) == 4 and f[3].endswith(".pcd") and f[2] == "label":
                obs_id = get_number(f[1])
                # read the label file
                with open(os.path.join(dirname, fl[:-3] + "txt"), "r") as label_file:
                    object_name = label_file.read()
                    object_name = object_name.strip()

                print "Got labled object '{}'".format(object_name)
                print object_name

                if object_name in live_objects:
                    live_objects.remove(object_name)

                if not world.does_object_exist(object_name):
                    object = world.create_object(object_name)
                    object._parent = room_object.name
                    object.add_identification("TRUTH",
                                              world_state.identification.ObjectIdentification(
                                                  {class_lookup[object_name]: 1,},
                                                  {object_name: 1,}))
                else:
                    object = world.get_object(object_name)

                """
                copy observation info we generated before and to this object observation
                this object also contains index info that can be retrieved
                """
                observation = world_state.observation.Observation.copy(observations[obs_id])
                src_cloud = observation.get_message("/head_xtion/depth_registered/points")
                stamp = src_cloud.header.stamp
                camera_pose = world_state.observation.TransformationStore.unpickle(
                    observation.get_message("/tf").msg)._transformations[0]
                time = rospy.Time(stamp.secs, stamp.nsecs).to_time()

                #when loading data form file time equals __life_start
                if time < object._life_start:
                    object._life_start = time

                # Find the pose of the object in the map frame...
                # t = world_state.geometry.Pose.from_ros_msg(camera_pose).as_homog_matrix()
                """
                read the point cloud and calculate the object center
                """
                cloud = python_pcd.io.read_pcd(os.path.join(dirname, fl), get_tf=False)
                cloud.header = src_cloud.header
                cent = np.array([0.0, 0.0, 0.0, 0.0])
                cnt = 0
                for pt in pc2.read_points(cloud):
                    cent += np.array(pt)
                    cnt += 1
                cent /= cnt
                print cent
                pose = world_state.geometry.Pose()

                pose.position.x, pose.position.y, pose.position.z, turd = cent
                object.add_pose(pose)
                observation.add_message(cloud, "object_cloud")
                object.add_observation(observation)

        # Any object not observed this time in the room should be marked dead
        for obj in live_objects:
            print "Did not see ", obj, " this time..."
            world.get_object(obj).cut(time)

def scan_dir(input_path, file_name, rooms):
    """
    scan through all the folders find the specified file name(*.xml),
    """
    # os.path.walk is deprecated and removed in python3, use os.walk() instead
    for absolute_path, folders, files in os.walk(input_path):
        if file_name in files:
            with open(os.path.join(absolute_path, file_name), "r") as f_handle:
                room = xmltodict.parse(f_handle)
            room_name = room['SemanticRoom']["RoomStringId"]
            rooms.append((absolute_path,
                          room_name,
                          files,
                          datetime.datetime.strptime(room['SemanticRoom']['RoomLogStartTime'],
                                                     "%Y-%b-%d %H:%M:%S.%f")))
    return

def scan_txt(input_path):
    """
    Go through all the folder under specified path to find txt file and extract the string append to a new file
    """
    # record objects in txt file
    object_list = []
    object_dic = {}

    for find_path, folders, files in os.walk(input_path):
        for txt in files:
            part = txt.split('_')
            if len(part) == 4 and part[3].endswith(".txt"):
                whole_file_path = os.path.join(find_path, txt)
                with open(whole_file_path, "r") as txt_reader:
                    object_name = txt_reader.read()
                    object_name = object_name.strip()

                    # check for duplicate member
                    if object_name not in object_list:
                        object_list.append(object_name)

                        # write in a dictionary format for convenience
                        if object_name[-1].isdigit():
                            for x in range(2, len(object_name)):
                                if not object_name[-x].isdigit():
                                    object_dic[object_name] = object_name[:-x+1]
                                    break
                        else:
                            object_dic[object_name] = object_name
    return object_dic

if __name__ == '__main__':

    #path to the data sets
    ROMBUS_DB = "/Volumes/BIG_ANOKK/strands_data_backup/20150505"

    #scan all the labeled objects and put them in a dict
    class_lookup = scan_txt(ROMBUS_DB)

    rospy.init_node("data_importer", anonymous=True)

    # connect DB, ready to add object
    world = world_state.state.World()

    rooms = []
    scan_dir(ROMBUS_DB, "room.xml", rooms)

    rooms.sort(key=lambda x: x[-1])

    for i, r in enumerate(rooms):
        print "-" * 20
        print "[%d/%d]" % (i, len(rooms)), r[0], "\t\t", r[-1]
        print "\n" * 5
        # r[0] is the the absolute path, r[2] all the file under that folder
        parse_room(world, r[0], r[2], class_lookup)
    raw_input("Done. Press return.")
