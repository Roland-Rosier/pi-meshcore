import importlib.util

print("aiologic: available" if importlib.util.find_spec("aiologic") else "aiologic: NOT available")

try:
    from pi_lora.drivers.rfm9x_sx127x_config_loader import (
        load_config,
        load_family_config,
    )
    c = load_config()
    f = load_family_config()
    print("sync public functions: OK", len(c.devices), len(f.families))
except Exception as e:
    print("sync public functions: FAILED ->", e)
