import os
import re
import shutil
from datetime import datetime as dt
from pathlib import Path
from typing import List

import hydra
import pypdf
from omegaconf import DictConfig


@hydra.main(version_base=None, config_path="../conf", config_name="config")
def start(cfg: DictConfig):
    read_format = cfg.parser.datereadformat
    write_format = cfg.parser.datewriteformat
    target_path = Path(cfg.parser.targetpath)
    extracted_data = []

    for filePath in [Path(file) for file in cfg.parser.src]:
        if filePath.is_dir():
            for file in [
                x for x in filePath.iterdir() if x.name.endswith(".pdf") and x.is_file()
            ]:
                extracted_data.append(extract_data(file, read_format))

        elif filePath.is_file():
            extracted_data.append(extract_data(filePath, read_format))
        else:
            raise ValueError("Something went wrong ")

        for file in extracted_data:
            if (
                file.get("vorgang") is None
                or file.get("date") is None
                or file.get("ISIN") is None
            ):
                print("Something went wrong with %s" % file.get("name"))
            else:
                write_file(file, target_path, write_format)


def extract_data(file: Path, readformat: str) -> dict:
    date_found = False

    file_data = {}
    file_data["name"] = str(file)
    file_data["content"] = pypdf.PdfReader(file).pages[0].extract_text()
    content: list[str] = file_data["content"].split("\n")

    for line in content:
        if "Wertpapierabrechnung: " in line:
            if file_data.get("vorgang") is None:
                file_data["vorgang"] = line.split(": ")[1]
            else:
                raise ValueError(
                    "found multiple 'vorgang' candidates in %s" % file_data["name"]
                )

        elif "Ausschüttung" in line:
            if file_data.get("vorgang") is None:
                file_data["vorgang"] = line
            else:
                if not file_data["vorgang"] == line:
                    raise ValueError(
                        "found multiple 'vorgang' candidates in %s found %s %s "
                        % file_data["name"],
                        line,
                        file_data["vorgang"],
                    )

        elif (
            not date_found
            and re.match("[0-9]{2}\.[0-9]{2}\.[0-9]{4}", line) is not None
        ):
            file_data["date"] = dt.strptime(line, readformat)
            date_found = True

        elif "ISIN: " in line:
            file_data["ISIN"] = line.split(": ")[1]
        else:
            pass

    return file_data


def write_file(file_data: dict, targetPath: Path, write_format) -> None:
    new_name = (
        dt.strftime(file_data["date"], write_format)
        + "_"
        + file_data["ISIN"]
        + "_"
        + file_data["vorgang"]
        + ".pdf"
    )
    shutil.copy2(file_data["name"], Path(targetPath / new_name))


if __name__ == "__main__":
    start()
