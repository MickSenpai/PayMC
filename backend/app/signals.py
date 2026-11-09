from dataclasses import asdict, dataclass, field

SEVERITY_WEIGHT = {"info": 0, "low": 10, "medium": 30, "high": 50}


@dataclass
class Signal:
    code: str
    severity: str  # info | low | medium | high
    message: str
    source: str  # paypal_api | message_analysis | internal_velocity | provider
    evidence: dict = field(default_factory=dict)


@dataclass
class Verdict:
    status: str  # verified | review_required | high_risk
    score: int
    action: str
    signals: list[Signal]

    def to_dict(self) -> dict:
        return {**asdict(self), "signals": [asdict(s) for s in self.signals]}


def build_verdict(signals: list[Signal], *, verifiable: bool = True) -> Verdict:
    """Veredicto explicable a partir de señales.

    - high_risk: >=2 señales altas o puntuación >= 80
    - review_required: cualquier señal >= low, o no se pudo verificar
    - verified: sin señales relevantes y verificado contra la fuente oficial
    """
    score = min(100, sum(SEVERITY_WEIGHT[s.severity] for s in signals))
    highs = sum(1 for s in signals if s.severity == "high")
    if highs >= 2 or score >= 80:
        status, action = "high_risk", "Detener el flujo (no entregar) y revisar manualmente."
    elif score > 0 or not verifiable:
        status, action = "review_required", "Solicitar comprobaciones adicionales o revisar manualmente."
    else:
        status, action = "verified", "Continuar: las comprobaciones implementadas coinciden."
    return Verdict(status, score, action, signals)
