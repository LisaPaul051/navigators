import numpy as np
import rospy
from common import COMPASS_UNCERTAINTY, GNSS_TOPIC, IMU_TOPIC, get_yaw_from_imu
from ekf_measurement import (
    CompassMeasurement,
    LocationMeasurement,
    combine_measurements,
)
from gps import GPSHandler, GPSLocation, GPSReceiver
from pose import Pose3D
from sensor_msgs.msg import Imu, NavSatFix
from sensors import get_initial_compass_reading


class Robot:
    def __init__(self):
        self.initial_compass = get_initial_compass_reading()
        self.pose: Pose3D = Pose3D.from_values(0, 0, self.initial_compass)
        self.cov: np.ndarray = np.diagonal([0.05, 0.05, 0.1])

        self.location_measurement: LocationMeasurement = None
        self.gps_receiver = GPSReceiver(GNSS_TOPIC, custom_callback=self.gps_callback)
        self.gps_handler = self.gps_receiver.create_handler(init_sleep_s=3)

        self.compass_measurement: CompassMeasurement = None
        rospy.Subscriber(IMU_TOPIC, Imu, self.compass_cb)

        # Run EKF at the given frequency
        rospy.Timer(0.1, self.ekf_step)

    def gps_callback(self, msg: NavSatFix):
        """Convert a NavSatFix to a XY and store the location measurement."""
        gps_position = GPSLocation.from_lat_lon(msg.latitude, msg.longitude)

        xy = self.gps_handler.get_xy(gps_position)
        self.location_measurement = LocationMeasurement(xy.reshape((1, 2)))

    def compass_callback(self, message: Imu):
        """Store compass value."""
        self.compass_measurement = CompassMeasurement(
            np.array(get_yaw_from_imu(message)).reshape((1, 1))
        )

    def get_measurements(self):
        return [self.compass_measurement, self.location_measurement]

    def ekf_update(self):
        not_used_ms = [
            m for m in self.get_measurements() if m is not None and not m.used
        ]

        z, R, H, V, h = combine_measurements(not_used_ms, self.pose)

        P_bar = self.cov

        K_gain = P_bar @ H.T @ np.linalg.inv(H @ P_bar @ H.T + V @ R @ V.T)
        new_pose = self.pose + K_gain @ (z - h)

        I = np.identity((K_gain @ H).shape[0])
        new_cov = (I - K_gain @ H) @ P_bar @ (I - K_gain @ H).T

        for m in not_used_ms:
            m.used = True

        return new_pose, new_cov

    def ekf_step(self):
        """Perform the EKF prediction and update."""

        # Prediction from odometry?

        # Update using measurements
        self.pose, self.cov = self.ekf_update()
