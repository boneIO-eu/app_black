"""The 1.6.43 plan switches log2ram to cp with exactly one config line."""

from boneio.migrations.actions import AppendLineIfMissing
from boneio.migrations.versions import v1_6_43_log2ram_cp as m


def test_plan_appends_use_rsync_false():
    assert m.plan() == [
        AppendLineIfMissing(path="/etc/log2ram.conf", line="USE_RSYNC=false")
    ]
