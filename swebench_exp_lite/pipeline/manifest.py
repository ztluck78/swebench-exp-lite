"""Manifest：单 json 记录六阶段 status / 产物 / 时间戳，支持断点续跑。

精简自主仓 core/manifest.py：只保留 pipeline 续跑所需的
set_meta / mark_started / mark_done / statuses / set_image / save，
去掉 attempts / workspace_meta / killed 追踪等批量实验设施。

文件落点：`output/<instance_id>/manifest.json`（与产物同目录，自包含）。
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Manifest:
    def __init__(self, task_dir: Path):
        self.task_dir = Path(task_dir)
        self.path = self.task_dir / "manifest.json"
        self.data = {
            "instance_id": self.task_dir.name,
            "run_id": None,
            "model": None,
            "created": None,
            "updated": None,
            "image": None,
            "stages": {},  # name -> {status, started, finished, outputs:[]}
        }
        if self.path.exists():
            try:
                self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
            except Exception:  # 损坏则备份保留现场并告警
                bak = self.path.with_name(
                    f"manifest.bak-{int(datetime.now().timestamp())}.json")
                try:
                    self.path.rename(bak)
                    print(f"[manifest] 警告：{self.path.name} 解析失败，"
                          f"已备份为 {bak.name}，从头开始记录", file=sys.stderr)
                except Exception:  # noqa: BLE001
                    pass

    def save(self) -> None:
        self.data["updated"] = _now()
        content = json.dumps(self.data, indent=2, ensure_ascii=False)
        # 临时文件名带 pid + 纳秒时间戳，避免并发撞名
        tmp = self.path.with_name(
            f"{self.path.stem}.tmp-{os.getpid()}-{int(time.time() * 1e6)}.json"
        )
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, self.path)

    def set_meta(self, run_id: str, model: str, dataset: str | None = None,
                 split: str | None = None) -> None:
        self.data["run_id"] = run_id
        self.data["model"] = model
        if dataset is not None:
            self.data["dataset"] = dataset
        if split is not None:
            self.data["split"] = split
        if not self.data.get("created"):
            self.data["created"] = _now()
        self.save()

    def set_image(self, image_data: dict) -> None:
        self.data["image"] = image_data
        self.save()

    def _stage(self, name: str) -> dict:
        return self.data["stages"].setdefault(
            name, {"status": "pending", "started": None, "finished": None, "outputs": []})

    def mark_started(self, name: str) -> None:
        st = self._stage(name)
        st["status"] = "running"
        # 重跑（断点续跑/force）时重置计时并清空旧产物记录，避免负耗时
        st["started"] = _now()
        st["finished"] = None
        st["outputs"] = []
        st.pop("error", None)
        self.save()

    def mark_done(self, name: str, outputs: list[str] | None = None) -> None:
        st = self._stage(name)
        st["status"] = "done"
        st["finished"] = _now()
        if outputs is not None:
            st["outputs"] = outputs
        self.save()

    def mark_failed(self, name: str, error: str = "") -> None:
        st = self._stage(name)
        st["status"] = "failed"
        st["finished"] = _now()
        if error:
            st["error"] = error
        self.save()

    def statuses(self) -> dict[str, str]:
        return {name: st.get("status", "pending")
                for name, st in self.data.get("stages", {}).items()}

    def is_done(self, name: str) -> bool:
        return self._stage(name).get("status") == "done"

    def all_stages(self) -> dict:
        return dict(self.data.get("stages", {}))
