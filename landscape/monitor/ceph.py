import time
import os

from landscape.accumulate import Accumulator
from landscape.lib.monitor import CoverageMonitor
from landscape.lib.command import run_command, CommandError
from landscape.monitor.plugin import MonitorPlugin

ACCUMULATOR_KEY = "ceph-usage-accumulator"
CEPH_CONFIG_FILE = "/etc/ceph/ceph.conf"


class CephUsage(MonitorPlugin):
    """
    Plugin that captures Ceph usage information. This only works if the client
    runs on one of the Ceph monitor nodes, and it noops otherwise.
    """
    persist_name = "ceph-usage"
    # Prevent the Plugin base-class from scheduling looping calls.
    run_interval = None

    def __init__(self, interval=30, monitor_interval=60 * 60,
                 create_time=time.time):
        self._interval = interval
        self._monitor_interval = monitor_interval
        self._ceph_usage_points = []
        self._ceph_ring_id = None
        self._create_time = create_time
        self._ceph_config = CEPH_CONFIG_FILE

    def register(self, registry):
        super(CephUsage, self).register(registry)
        self._accumulate = Accumulator(self._persist, registry.step_size)

        self.registry.reactor.call_every(self._interval, self.run)

        self._monitor = CoverageMonitor(self._interval, 0.8,
                                        "Ceph usage snapshot",
                                        create_time=self._create_time)
        self.registry.reactor.call_every(self._monitor_interval,
                                         self._monitor.log)
        self.registry.reactor.call_on("stop", self._monitor.log, priority=2000)
        self.call_on_accepted("ceph-usage", self.send_message, True)

    def create_message(self):
        ceph_points = self._ceph_usage_points
        ring_id = self._ceph_ring_id
        self._ceph_usage_points = []
        return {"type": "ceph-usage", "ceph-usages": ceph_points,
                "ring-id": ring_id}

    def send_message(self, urgent=False):
        message = self.create_message()
        if message["ceph-usages"] and message["ring-id"] is not None:
            self.registry.broker.send_message(message, urgent=urgent)

    def exchange(self, urgent=False):
        self.registry.broker.call_if_accepted("ceph-usage",
                                              self.send_message, urgent)

    def run(self):
        self._monitor.ping()

        config_file = self._ceph_config
        # Check if a ceph config file is available. No need to run anything
        # if we know that we're not on a Ceph monitor node anyway.
        if not os.path.exists(config_file):
            # There is no config file - it's not a ceph machine.
            return None

        # Extract the ceph ring Id and cache it.
        if self._ceph_ring_id is None:
            self._ceph_ring_id = self._get_ceph_ring_id()

        new_timestamp = int(self._create_time())
        new_ceph_usage = self._get_ceph_usage()

        step_data = None
        if new_ceph_usage is not None:
            step_data = self._accumulate(new_timestamp, new_ceph_usage,
                                        ACCUMULATOR_KEY)
        if step_data is not None:
            self._ceph_usage_points.append(step_data)

    def _get_ceph_usage(self):
        """
        Grab the ceph usage data by parsing the output of the "ceph status"
        command output.
        """
        output = self._get_ceph_command_output()

        if output is None:
            return None

        lines = output.split("\n")

        pg_line = None
        for line in lines:
            if "pgmap" in line:
                pg_line = line.split()
                break

        if pg_line is None:
            return None

        total = pg_line[-3]  # Total space
        available = pg_line[-6]  # Available for objects
        #used = pg_line[-9]  # Used by objects
        # Note: used + available is NOT equal to total (there is some used
        # space for duplication and system info etc...)

        filled = int(total) - int(available)

        return filled / float(total)

    def _get_ceph_command_output(self):
        try:
            output = run_command("ceph status")
        except (OSError, CommandError):
            # If the command line client isn't available, we assume it's not
            # a ceph monitor machine.
            return None
        return output

    def _get_ceph_ring_id(self):
        output = self._get_quorum_command_output()
        lines = output.split("\n")
        fsid_line = None
        for line in lines:
            if "fsid" in line:
                fsid_line = line.split()
                break

        if fsid_line is None:
            return None

        wrapped_id = fsid_line[-1]
        ring_id = wrapped_id.replace('",', '')
        ring_id = ring_id.replace('"', '')

        return ring_id

    def _get_quorum_command_output(self):
        try:
            output = run_command("ceph quorum_status")
        except (OSError, CommandError):
            # If the command line client isn't available, we assume it's not
            # a ceph monitor machine.
            return None
        return output
