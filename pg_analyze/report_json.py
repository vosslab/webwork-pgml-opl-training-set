# Standard Library
import json
import os


#============================================


def write_report_json(json_out_dir: str, file_path: str, report: dict) -> str:
	out_path = os.path.join(json_out_dir, file_path + ".json")
	out_dir = os.path.dirname(out_path)
	if out_dir:
		os.makedirs(out_dir, exist_ok=True)
	with open(out_path, "w", encoding="utf-8") as f:
		json.dump(report, f, indent=2, ensure_ascii=True)
		f.write("\n")
	return out_path

