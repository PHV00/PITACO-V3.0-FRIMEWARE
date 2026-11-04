# Configuracoes originais do PITACO Bridge.
import os
import json

def get_config_path():
    appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    config_dir = os.path.join(appdata, "PITACO_Bridge")
    try:
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "config_mpx5010dp.json")
    except:
        return "config_mpx5010dp.json"

DEFAULT_PROFILE_DATA = {
    "max_flow": 100.0,
    "min_flow": -100.0,
    "resp_rate": 0.0,
    "t_ins": 0.0,
    "t_exp": 0.0,
    "ie_ratio": "1:2.0",
    "last_updated": "Nunca"
}

DEFAULT_CONFIG = {
    "active_profile": "Padrão",
    "profiles": {
        "Padrão": DEFAULT_PROFILE_DATA.copy()
    },
    "com0com_installed": False,
    "conn_mode": "Cabo USB",
    "output_mode": "Pressão relativa (Pa)",
    "filter_mode": "Moderado",
    "scale_multiplier": 5.0,
    "scale_key": "5.0x",
    "game_port": "Somente monitor",
    "device_port": ""
}

def load_config():
    p = get_config_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                cfg = DEFAULT_CONFIG.copy()
                cfg.update(data)

                # Garante estrutura de profiles
                if "profiles" not in cfg or not isinstance(cfg["profiles"], dict) or not cfg["profiles"]:
                    cfg["profiles"] = {"Padrão": DEFAULT_PROFILE_DATA.copy()}

                for prof_name, prof_dict in list(cfg["profiles"].items()):
                    merged_prof = DEFAULT_PROFILE_DATA.copy()
                    if isinstance(prof_dict, dict):
                        merged_prof.update(prof_dict)
                    cfg["profiles"][prof_name] = merged_prof

                if cfg.get("active_profile") not in cfg["profiles"]:
                    cfg["active_profile"] = list(cfg["profiles"].keys())[0]

                return cfg
        except Exception as e:
            print(f"Erro ao carregar config.json: {e}")
    return DEFAULT_CONFIG.copy()
