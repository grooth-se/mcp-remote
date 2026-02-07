"""Models for measured thermocouple data from heat treatment logging."""
from datetime import datetime
from typing import List, Dict, Optional
import json

from app import db


class MeasuredData(db.Model):
    """Measured thermocouple data from heat treatment logging.

    Stores uploaded CSV data from temperature loggers with up to 8 channels.
    Can be linked to a simulation for comparison.
    """
    __bind_key__ = 'materials'
    __tablename__ = 'measured_data'

    id = db.Column(db.Integer, primary_key=True)
    simulation_id = db.Column(db.Integer, db.ForeignKey('simulations.id'), nullable=True)

    # Metadata
    name = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    filename = db.Column(db.Text)  # Original uploaded filename

    # Time range
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    duration_seconds = db.Column(db.Float)

    # Channel info (JSON: {TC1: "Surface", TC2: "Furnace", ...})
    channel_labels = db.Column(db.Text)

    # Data storage (JSON arrays)
    # times: seconds from start (reference channel, for backwards compatibility)
    # channel_times: {TC1: [times], TC2: [times], ...} - per-channel times
    # channels: {TC1: [temps], TC2: [temps], ...}
    times_json = db.Column(db.Text)
    channel_times_json = db.Column(db.Text)
    channels_json = db.Column(db.Text)

    # Statistics per channel (JSON: {TC1: {min, max, avg}, ...})
    statistics_json = db.Column(db.Text)

    # Timestamps
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    simulation = db.relationship('Simulation', backref=db.backref('measured_data', lazy='dynamic'))

    @property
    def channel_labels_dict(self) -> Dict[str, str]:
        """Get channel labels as dict."""
        if self.channel_labels:
            return json.loads(self.channel_labels)
        return {}

    @channel_labels_dict.setter
    def channel_labels_dict(self, labels: Dict[str, str]):
        """Set channel labels from dict."""
        self.channel_labels = json.dumps(labels)

    @property
    def times(self) -> List[float]:
        """Get time array."""
        if self.times_json:
            return json.loads(self.times_json)
        return []

    @times.setter
    def times(self, times: List[float]):
        """Set time array."""
        self.times_json = json.dumps(times)

    @property
    def channels(self) -> Dict[str, List[float]]:
        """Get channel data as dict."""
        if self.channels_json:
            return json.loads(self.channels_json)
        return {}

    @channels.setter
    def channels(self, channels: Dict[str, List[float]]):
        """Set channel data from dict."""
        self.channels_json = json.dumps(channels)

    @property
    def channel_times(self) -> Dict[str, List[float]]:
        """Get per-channel times as dict."""
        if self.channel_times_json:
            return json.loads(self.channel_times_json)
        # Fallback to unified times for all channels
        if self.times_json:
            unified_times = json.loads(self.times_json)
            return {ch: unified_times for ch in self.channels.keys()}
        return {}

    @channel_times.setter
    def channel_times(self, channel_times: Dict[str, List[float]]):
        """Set per-channel times from dict."""
        self.channel_times_json = json.dumps(channel_times)

    def get_channel_times(self, channel: str) -> List[float]:
        """Get times array for a specific channel."""
        ct = self.channel_times
        if channel in ct:
            return ct[channel]
        # Fallback to unified times
        return self.times

    @property
    def statistics(self) -> Dict[str, Dict[str, float]]:
        """Get statistics per channel."""
        if self.statistics_json:
            return json.loads(self.statistics_json)
        return {}

    @statistics.setter
    def statistics(self, stats: Dict[str, Dict[str, float]]):
        """Set statistics."""
        self.statistics_json = json.dumps(stats)

    @property
    def available_channels(self) -> List[str]:
        """Get list of available channel names."""
        return list(self.channels.keys())

    @property
    def num_channels(self) -> int:
        """Get number of channels."""
        return len(self.channels)

    @property
    def num_points(self) -> int:
        """Get number of data points."""
        return len(self.times)

    def get_channel_data(self, channel: str) -> Optional[List[float]]:
        """Get temperature data for a specific channel."""
        return self.channels.get(channel)

    def get_channel_label(self, channel: str) -> str:
        """Get label for a channel, or channel name if no label."""
        labels = self.channel_labels_dict
        return labels.get(channel, channel)

    def __repr__(self):
        return f'<MeasuredData {self.id}: {self.name}>'
