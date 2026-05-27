from __future__ import annotations
import re
from pathlib import Path

def pack_architecture(unpacked_path: str | Path) -> Path:
    unpacked_path = Path(unpacked_path)
    filename = unpacked_path.name
    match = re.match(r"^unpacked[._-]([^.]+)\.pack$", filename, re.IGNORECASE)
    if not match:
        raise ValueError(f"El nombre del archivo debe seguir el formato 'unpacked.<arch>.pack', obtenido: {filename}")
    
    arch = match.group(1)
    dir_path = unpacked_path.parent
    
    # Buscar todos los subpacks correspondientes a la arquitectura
    subpack_paths = sorted(list(dir_path.glob(f"{arch}.*.pack")))
    
    # Mapeo y normalización de secciones
    section_map = {
        "world": "world",
        "type": "types",
        "types": "types",
        "word": "words",
        "words": "words",
        "reg": "regs",
        "regs": "regs",
        "macro": "macros",
        "macros": "macros",
        "rule": "rules",
        "rules": "rules"
    }
    
    sections_content: dict[str, list[str]] = {
        "world": [],
        "types": [],
        "words": [],
        "regs": [],
        "macros": [],
        "rules": []
    }
    
    section_re = re.compile(r"^\.([A-Za-z_][A-Za-z0-9_]*)$")
    
    # Incluir el archivo unpacked base si contiene información
    all_paths = []
    if unpacked_path.exists() and unpacked_path.stat().st_size > 0:
        all_paths.append(unpacked_path)
    all_paths.extend(subpack_paths)
    
    for sub_path in all_paths:
        current_section = None
        with open(sub_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                comment_stripped = stripped.split(";", 1)[0].strip()
                sec_match = section_re.fullmatch(comment_stripped)
                if sec_match:
                    sec_name = sec_match.group(1).lower()
                    current_section = section_map.get(sec_name)
                    continue
                
                if current_section is not None:
                    sections_content[current_section].append(line)
    
    # Escribir el pack unificado
    output_path = dir_path / f"{arch}.pack"
    ordered_sections = ["world", "types", "words", "regs", "macros", "rules"]
    
    with open(output_path, "w", encoding="utf-8") as out_f:
        first_section = True
        for sec in ordered_sections:
            lines = sections_content[sec]
            if lines:
                if not first_section:
                    out_f.write("\n")
                out_f.write(f".{sec}\n")
                first_section = False
                for line in lines:
                    out_f.write(line)
                    if not line.endswith("\n"):
                        out_f.write("\n")
                        
    return output_path
