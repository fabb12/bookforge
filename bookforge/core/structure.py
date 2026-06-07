"""Mappa dell'argomentazione: struttura il ragionamento prima della prosa.

Tesi → Argomenti → (Prove, Obiezioni, Repliche). Pensata per la saggistica:
aiuta l'esperto a *ragionare* e a controllare la solidità prima di scrivere.
Serializzabile in JSON e convertibile in una scaletta/elenco di concetti.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Argument:
    claim: str = ""
    evidence: list[str] = field(default_factory=list)
    objections: list[str] = field(default_factory=list)
    replies: list[str] = field(default_factory=list)


@dataclass
class ArgumentMap:
    thesis: str = ""
    arguments: list[Argument] = field(default_factory=list)

    # ---------- serializzazione ----------
    def to_dict(self) -> dict:
        return {"thesis": self.thesis,
                "arguments": [asdict(a) for a in self.arguments]}

    @staticmethod
    def from_dict(d: dict | None) -> "ArgumentMap":
        d = d or {}
        args = []
        for a in d.get("arguments", []):
            args.append(Argument(
                claim=a.get("claim", ""),
                evidence=list(a.get("evidence", [])),
                objections=list(a.get("objections", [])),
                replies=list(a.get("replies", [])),
            ))
        return ArgumentMap(thesis=d.get("thesis", ""), arguments=args)

    def is_empty(self) -> bool:
        return not self.thesis.strip() and not self.arguments

    # ---------- conversioni ----------
    def to_outline(self) -> str:
        """Rende la mappa come testo gerarchico leggibile."""
        lines: list[str] = []
        if self.thesis:
            lines.append(f"TESI: {self.thesis}")
        for i, a in enumerate(self.arguments, 1):
            lines.append(f"\nArgomento {i}: {a.claim}")
            for e in a.evidence:
                lines.append(f"  • prova: {e}")
            for o in a.objections:
                lines.append(f"  ⚠ obiezione: {o}")
            for r in a.replies:
                lines.append(f"  ↳ replica: {r}")
        return "\n".join(lines).strip()

    def to_ai_format(self) -> str:
        """Formato editabile a righe (TESI/ARGOMENTO/PROVA/OBIEZIONE/REPLICA).

        Round-trippa con `parse_ai_map`: è quello mostrato nell'editor della mappa."""
        lines: list[str] = [f"TESI: {self.thesis}"]
        for a in self.arguments:
            lines.append(f"ARGOMENTO: {a.claim}")
            for e in a.evidence:
                lines.append(f"PROVA: {e}")
            for o in a.objections:
                lines.append(f"OBIEZIONE: {o}")
            for r in a.replies:
                lines.append(f"REPLICA: {r}")
        return "\n".join(lines)

    def to_concepts(self) -> str:
        """Trasforma la mappa in concetti grezzi (uno per riga) per il Writer."""
        lines: list[str] = []
        if self.thesis:
            lines.append(self.thesis)
        for a in self.arguments:
            if a.claim:
                lines.append(a.claim)
            lines.extend(a.evidence)
            for o in a.objections:
                lines.append(f"Obiezione: {o}")
            for r in a.replies:
                lines.append(f"Replica: {r}")
        return "\n".join(l for l in lines if l.strip())


def parse_ai_map(text: str) -> ArgumentMap:
    """Interpreta l'output testuale dell'AI in una ArgumentMap.

    Formato atteso (tollerante):
        TESI: ...
        ARGOMENTO: ...
        PROVA: ...
        OBIEZIONE: ...
        REPLICA: ...
    """
    amap = ArgumentMap()
    cur: Argument | None = None
    for raw in (text or "").splitlines():
        line = raw.strip().lstrip("-•*").strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("tesi"):
            amap.thesis = line.split(":", 1)[-1].strip()
        elif low.startswith("argoment"):
            cur = Argument(claim=line.split(":", 1)[-1].strip())
            amap.arguments.append(cur)
        elif low.startswith("prova") or low.startswith("evidenza"):
            if cur is None:
                cur = Argument(); amap.arguments.append(cur)
            cur.evidence.append(line.split(":", 1)[-1].strip())
        elif low.startswith("obiezion"):
            if cur is None:
                cur = Argument(); amap.arguments.append(cur)
            cur.objections.append(line.split(":", 1)[-1].strip())
        elif low.startswith("replic"):
            if cur is None:
                cur = Argument(); amap.arguments.append(cur)
            cur.replies.append(line.split(":", 1)[-1].strip())
    return amap
