import json
from pathlib import Path

def load_config(config_file="config/pipeline_config.json"):
    config_path = Path(__file__).resolve().parent.parent / config_file
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)

def get_schema_path():
    return Path(__file__).parent / "JSON_Schema_enhanced.json"
    
# ’Ç‰Á:
def load_pipeline_config(config_file="config/pipeline_config.json"):
    return load_config(config_file)