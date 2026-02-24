from surface_mapper.render3d.preview import _set_north_up_camera


class _FakeCamera:
    def __init__(self) -> None:
        self.focal_point = None
        self.position = None
        self.view_up = None
        self.parallel_projection = None
        self.parallel_scale = None

    def SetFocalPoint(self, x, y, z) -> None:
        self.focal_point = (x, y, z)

    def SetPosition(self, x, y, z) -> None:
        self.position = (x, y, z)

    def SetViewUp(self, x, y, z) -> None:
        self.view_up = (x, y, z)

    def SetParallelProjection(self, value) -> None:
        self.parallel_projection = bool(value)

    def SetParallelScale(self, value) -> None:
        self.parallel_scale = float(value)


class _FakePlotter:
    def __init__(self) -> None:
        self.camera = _FakeCamera()


def test_set_north_up_camera_uses_vtk_setters() -> None:
    plotter = _FakePlotter()
    _set_north_up_camera(plotter, bounds=(-10.0, 20.0, 5.0, 25.0, -1.0, 4.0), base_z=0.0)

    assert plotter.camera.focal_point == (5.0, 15.0, 0.0)
    assert plotter.camera.position[0] == 5.0
    assert plotter.camera.position[1] == 15.0
    assert plotter.camera.position[2] > 0.0
    assert plotter.camera.view_up == (0.0, 1.0, 0.0)
    assert plotter.camera.parallel_projection is True
    assert plotter.camera.parallel_scale > 0.0

