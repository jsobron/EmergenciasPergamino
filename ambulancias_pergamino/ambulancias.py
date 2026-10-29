from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Ambulancia:
    id: str
    base_id: str
    nodo_id: str
    disponible: bool
    complejidad: int
    capacidad_pacientes: int
    equipamiento: list[Any]


def _entero_positivo(valor: Any, campo: str, ambulancia_id: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ValueError(
            f"Ambulancia {ambulancia_id}: {campo} debe ser un entero mayor que cero"
        )
    return valor


def cargar_ambulancias(
    configuracion: Path, bases: list[dict[str, Any]]
) -> list[Ambulancia]:
    datos = json.loads(configuracion.read_text(encoding="utf-8"))
    if datos.get("datos_simulados") is not True:
        raise ValueError("La configuración debe identificar los datos como simulados")

    crudas = datos.get("ambulancias")
    if not isinstance(crudas, list):
        raise ValueError("ambulancias debe ser una lista")
    if len(crudas) != 6:
        raise ValueError("La configuración debe contener exactamente seis ambulancias")

    bases_por_id = {base["id"]: base for base in bases}
    ids_vistos: set[str] = set()
    bases_vistas: set[str] = set()
    ambulancias: list[Ambulancia] = []

    for cruda in crudas:
        if not isinstance(cruda, dict):
            raise ValueError("Cada ambulancia debe ser un objeto")
        ambulancia_id = cruda.get("id")
        if not isinstance(ambulancia_id, str) or not ambulancia_id.strip():
            raise ValueError("Cada ambulancia debe tener un ID de texto no vacío")
        if ambulancia_id in ids_vistos:
            raise ValueError(f"ID de ambulancia duplicado: {ambulancia_id}")
        ids_vistos.add(ambulancia_id)

        base_id = cruda.get("base_id")
        if base_id not in bases_por_id:
            raise ValueError(f"Ambulancia {ambulancia_id}: base inexistente {base_id!r}")
        if base_id in bases_vistas:
            raise ValueError(f"Base {base_id}: hay más de una ambulancia asignada")
        bases_vistas.add(base_id)

        disponible = cruda.get("disponible")
        if not isinstance(disponible, bool):
            raise ValueError(f"Ambulancia {ambulancia_id}: disponible debe ser booleano")
        equipamiento = cruda.get("equipamiento")
        if not isinstance(equipamiento, list):
            raise ValueError(f"Ambulancia {ambulancia_id}: equipamiento debe ser una lista")

        ambulancias.append(
            Ambulancia(
                id=ambulancia_id,
                base_id=base_id,
                nodo_id=bases_por_id[base_id]["nodo_id"],
                disponible=disponible,
                complejidad=_entero_positivo(
                    cruda.get("complejidad"), "complejidad", ambulancia_id
                ),
                capacidad_pacientes=_entero_positivo(
                    cruda.get("capacidad_pacientes"),
                    "capacidad_pacientes",
                    ambulancia_id,
                ),
                equipamiento=equipamiento.copy(),
            )
        )

    bases_sin_ambulancia = set(bases_por_id) - bases_vistas
    if bases_sin_ambulancia:
        faltantes = ", ".join(sorted(bases_sin_ambulancia))
        raise ValueError(f"Bases sin ambulancia: {faltantes}")
    return ambulancias
