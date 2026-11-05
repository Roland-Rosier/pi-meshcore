_ORDER: list[str] = []


def _order_capture(request) -> None:
    loc = str(request.node.location)
    path = loc.split("[")[0].strip()
    _ORDER.append(path)
    with open("/home/rpiuser/TestMeshcore/_order.txt", "w") as f:
        for i, p in enumerate(_ORDER):
            f.write(f"{i} {p}\n")
