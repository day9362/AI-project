"""平台当前生效的连接和规则。同步任务每次请求都读这里。"""

from dataclasses import dataclass

from core.config import settings as env


@dataclass
class LiveConfig:
    ready: bool = False
    source: str = "cluster"
    base_url: str = ""
    token: str = ""
    timeout_s: float = 20
    use_ground_truth: bool = False
    drift_c: float = 0.15
    degraded_alarm: bool = True
    sentinel_as_data_anomaly: bool = True


live = LiveConfig()


def apply_live(body: dict) -> None:
    source = body.get("source") or "cluster"
    cluster = body.get("cluster") or {}
    sim = body.get("sim") or {}
    rules = body.get("rules") or {}
    live.source = source
    live.base_url = str(sim.get("base_url") if source == "sim" else cluster.get("base_url") or "")
    live.token = "" if source == "sim" else str(cluster.get("token") or "")
    live.timeout_s = float(cluster.get("timeout_s") or env.cluster_timeout_s)
    live.use_ground_truth = bool(sim.get("use_ground_truth"))
    live.drift_c = float(rules.get("drift_c") if rules.get("drift_c") is not None else env.drift_c)
    live.degraded_alarm = bool(rules.get("degraded_alarm", env.degraded_alarm))
    live.sentinel_as_data_anomaly = bool(rules.get("sentinel_as_data_anomaly", env.sentinel_as_data_anomaly))
    live.ready = True


def endpoint() -> tuple[str, str, float]:
    if live.ready and live.base_url:
        return live.base_url.rstrip("/"), live.token, live.timeout_s
    return env.cluster_base_url.rstrip("/"), env.cluster_token, env.cluster_timeout_s
