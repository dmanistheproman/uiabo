"""Build a provisional real-topic retrieval set; never overwrite reviewer work."""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Each pair is a factual statement and a deliberately altered false statement.
# Sources were consulted on 2026-09-09. Labels require two human reviewers.
GROUPS = [
    ("moon_rotation", "astronomy", "development", "https://science.nasa.gov/moon/facts/",
     "The Moon rotates on its axis about once every 27 Earth days.",
     "The Moon rotates on its axis once every 24 hours."),
    ("moon_rings", "astronomy", "development", "https://science.nasa.gov/moon/facts/",
     "Earth's Moon has no rings.", "Earth's Moon has a ring system like Saturn's."),
    ("mars_moons", "astronomy", "development", "https://science.nasa.gov/mars/facts/",
     "Mars has two moons named Phobos and Deimos.", "Mars has three moons named Phobos, Deimos and Titan."),
    ("mars_order", "astronomy", "development", "https://science.nasa.gov/mars/facts/",
     "Mars is the fourth planet from the Sun.", "Mars is the second planet from the Sun."),
    ("venus_heat", "astronomy", "holdout", "https://science.nasa.gov/venus/venus-facts/",
     "Venus is the hottest planet in our solar system.", "Mercury is the hottest planet in our solar system."),
    ("venus_rotation", "astronomy", "holdout", "https://science.nasa.gov/venus/venus-facts/",
     "Venus takes longer to rotate once on its axis than to orbit the Sun once.",
     "Venus takes less time to rotate once on its axis than to orbit the Sun once."),
    ("ocean_water", "environment", "development", "https://oceanservice.noaa.gov/facts/oceanwater.html",
     "About 97 percent of Earth's water is in the ocean.", "About 7 percent of Earth's water is in the ocean."),
    ("ocean_surface", "environment", "development", "https://oceanservice.noaa.gov/facts/oceanwater.html",
     "The ocean covers more than 70 percent of Earth's surface.", "The ocean covers less than 30 percent of Earth's surface."),
    ("ice_density", "physics", "holdout", "https://www.usgs.gov/water-science-school/science/water-density",
     "Ordinary ice floats in liquid water because it is less dense than the water.",
     "Ordinary ice floats in liquid water because it is denser than the water."),
    ("declaration", "history", "holdout", "https://www.archives.gov/founding-docs/declaration-transcript",
     "The United States Declaration of Independence is dated July 4, 1776.",
     "The United States Declaration of Independence is dated July 4, 1876."),
    ("si_count", "measurement", "holdout", "https://www.nist.gov/pml/owm/metric-si/si-units",
     "The International System of Units has seven base units.", "The International System of Units has twelve base units."),
    ("si_mass", "measurement", "holdout", "https://www.nist.gov/pml/owm/metric-si/si-units",
     "The kilogram is the SI base unit of mass.", "The pound is the SI base unit of mass."),
    ("antibiotic_virus", "health", "development", "https://www.cdc.gov/antibiotic-use/about/index.html",
     "Antibiotics do not work against viruses.", "Antibiotics work against viruses."),
    ("antibiotic_cold", "health", "development", "https://www.cdc.gov/antibiotic-use/about/index.html",
     "Antibiotics do not treat the viruses that cause the common cold.",
     "Antibiotics cure the viruses that cause the common cold."),
    ("flower_year", "singapore", "development", "https://www.nparks.gov.sg/florafaunaweb/flora/2/5/2539",
     "Vanda Miss Joaquim was chosen as Singapore's national flower in 1981.",
     "Vanda Miss Joaquim was chosen as Singapore's national flower in 1991."),
    ("flower_identity", "singapore", "development", "https://www.nparks.gov.sg/florafaunaweb/flora/2/5/2539",
     "Singapore's national flower is Vanda Miss Joaquim.", "Singapore's national flower is the sunflower."),
    ("dengue_vector", "health", "holdout", "https://www.nea.gov.sg/dengue-zika/dengue",
     "Dengue can spread through the bite of an infected Aedes mosquito.",
     "Dengue cannot spread through mosquito bites."),
    ("canberra_name", "geography", "development", "https://www.nca.gov.au/education/canberras-history/siting-and-naming-canberra",
     "Canberra was officially named in 1913.", "Canberra was officially named in 2013."),
    ("canberra_capital", "geography", "development", "https://www.nca.gov.au/sites/default/files/8CanberraSeatofGovernment_0.pdf",
     "Canberra is Australia's capital city.", "Sydney is Australia's capital city."),
    ("web_invention", "technology", "holdout", "https://home.cern/science/computing/the-birth-of-the-web/",
     "Tim Berners-Lee invented the World Wide Web at CERN in 1989.",
     "Tim Berners-Lee invented the World Wide Web at CERN in 1969."),
]


def main():
    cases = []
    for group, topic, split, source, true_claim, false_claim in GROUPS:
        for outcome, claim in [("supported", true_claim), ("refuted", false_claim)]:
            cases.append({"id": group + "_" + outcome, "group": group, "topic": topic,
                "split": split, "claim": claim, "expected": outcome,
                "reference_urls": [source], "review_status": "pending_two_human_reviewers"})
    cases.extend([
        {"id": "phuket_personal", "group": "phuket", "topic": "travel", "split": "regression",
         "claim": "I need to have 20000 baht in cash to enter phuket", "expected": "insufficient",
         "reference_urls": ["https://doha.thaiembassy.org/en/publicservice/tourist-visa-exemption-visa-on-arrival?page=5d7e6a3c15e39c032c006dba"],
         "note": "Personal eligibility and entry scheme are missing; this is not a label saying the monetary rule is false.",
         "review_status": "pending_two_human_reviewers"},
        {"id": "great_wall_moon", "group": "great_wall", "topic": "astronomy", "split": "regression",
         "claim": "The Great Wall of China is visible from the Moon.", "expected": "refuted",
         "reference_urls": ["https://www.nasa.gov/image-article/great-wall/"],
         "review_status": "pending_two_human_reviewers"},
        {"id": "food_opinion", "group": "food_opinion", "topic": "opinion", "split": "regression",
         "claim": "Chicken rice is the best food in Singapore.", "expected": "insufficient", "reference_urls": [],
         "review_status": "pending_two_human_reviewers"},
    ])
    data = {"dataset_id": "retrieval_seed_v1", "created_at": "2026-09-09",
        "label_author": "Codex", "status": "provisional_not_independent_benchmark",
        "notes": "40 real-topic paired claims plus 3 known regressions. Sources/related pairs stay within a split. Reference URLs are reviewer guidance, NEVER supplied to retrieval or assessment. Model prompts and examples share an author. All labels need human review.",
        "cases": cases}
    (ROOT / "retrieval_seed_v1.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    review = ROOT / "retrieval_seed_v1_review.csv"
    if not review.exists():
        with review.open("w", newline="", encoding="utf-8-sig") as stream:
            fields = ["id", "claim", "reference_urls", "reviewer_1", "reviewer_2", "final_label",
                      "evidence_quote", "applicability_notes", "review_date"]
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for case in cases:
                writer.writerow({"id": case["id"], "claim": case["claim"], "reference_urls": " | ".join(case["reference_urls"])})
    print(f"Prepared {len(cases)} provisional cases; existing review CSV preserved.")


if __name__ == "__main__":
    main()
