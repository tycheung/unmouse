from unmouse.gaze.display import DisplayMapper, MonitorInfo, VirtualDesktop


def _dual_monitor_desktop() -> VirtualDesktop:
    primary = MonitorInfo(x=0, y=0, width=1920, height=1080, dpi_scale=1.0)
    secondary = MonitorInfo(x=1920, y=0, width=1280, height=720, dpi_scale=1.25)
    return VirtualDesktop(
        monitors=(primary, secondary),
        left=0,
        top=0,
        width=3200,
        height=1080,
    )


def test_clip_within_virtual_desktop_bounds() -> None:
    mapper = DisplayMapper(_dual_monitor_desktop())
    x, y = mapper.clip(4000.0, -10.0)
    assert x == 3199.0
    assert y == 0.0


def test_map_point_applies_monitor_dpi_scale() -> None:
    mapper = DisplayMapper(_dual_monitor_desktop())
    x, y = mapper.map_point(2000.0, 100.0)
    assert x == 2020.0
    assert y == 125.0


def test_monitor_selection_primary() -> None:
    mapper = DisplayMapper(_dual_monitor_desktop())
    monitor = mapper._monitor_for(100.0, 100.0)
    assert monitor is not None
    assert monitor.x == 0
