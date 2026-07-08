"""Test doubles shared across unit, integration, and E2E suites."""

from tests.fakes.broker import MockFrameSource
from tests.fakes.enrollment import FakeEnrollmentSession

__all__ = ["FakeEnrollmentSession", "MockFrameSource"]
