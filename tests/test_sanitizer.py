import argparse

import pytest

from triton_telemetry.sanitizer import parse_cluster_id, parse_timeout


@pytest.mark.parametrize("value,expected", [("0.1", 0.1), ("2.5", 2.5), ("5.0", 5.0)])
def test_timeout_valido(value, expected):
    assert parse_timeout(value) == pytest.approx(expected)


@pytest.mark.parametrize("value", ["0.05", "9.5", "0", "abc", ""])
def test_timeout_invalido(value):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_timeout(value)


@pytest.mark.parametrize(
    "value", ["cluster-us-east-01", "cluster-eu-west-02", "cluster-us-01", "cluster-sa-east-1"]
)
def test_cluster_valido(value):
    assert parse_cluster_id(value) == value


@pytest.mark.parametrize("value", ["cluster-invalido-id", "cluster-", "CLUSTER-US-EAST-01", "us-east-01", ""])
def test_cluster_invalido(value):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_cluster_id(value)
