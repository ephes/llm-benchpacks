from __future__ import annotations

import argparse
import csv
import json
import math
import re
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable


WEIGHTS = [
    0.0,
    0.407635222342,
    0.378648088997,
    0.229915471353,
    0.49406094705,
    0.081330598314,
    0.231416767381,
    -0.003710135566,
    0.180386178781,
    -0.027784814396,
    -0.275042266553,
    -0.072068698894,
    -0.315067763357,
    -0.168676030026,
    -0.542720302071,
    0.10551597963,
]
MEANS = [
    1.0,
    0.177245704283,
    0.359575417593,
    0.290809520883,
    0.094943426454,
    0.081596074897,
    0.182016621608,
    0.050465605287,
    0.089349904876,
    0.408180634825,
    0.207815159708,
    0.124261540002,
    0.233628717333,
    0.283843997196,
    0.532566687914,
    0.211362020627,
]
STDS = [
    1.0,
    0.179206230062,
    0.269975680019,
    0.177625791779,
    0.196034273687,
    0.146064098922,
    0.400789021701,
    0.226303138593,
    0.165063109158,
    0.491496901495,
    0.405743785046,
    0.329879689703,
    0.42313867676,
    0.450862043703,
    0.520079359565,
    0.202158448404,
]

PAIR_RANK_WEIGHTS = [
    -3.599494671,
    0.0,
    0.901405305,
    0.419210619,
    0.419210619,
    1.065019559,
    -0.468312261,
    -0.036166917,
    -0.380396414,
    0.030985443,
    0.055850975,
    -0.946293258,
    -0.921540114,
    -1.171798202,
    -0.397040498,
    0.29739739,
    0.481537787,
    -0.133165038,
    0.047855717,
    0.38947221,
    -0.325106737,
    -1.363383608,
    -0.169217995,
    -2.747593464,
]
PAIR_RANK_MEANS = [
    1.0,
    0.143447126,
    0.28161634,
    0.28161634,
    0.070206438,
    0.105218411,
    0.200689415,
    0.079392851,
    0.08666068,
    0.244041481,
    0.259521465,
    0.227454956,
    0.231272812,
    0.330734025,
    0.522123519,
    0.170190893,
    0.11756561,
    0.03116853,
    0.106059904,
    0.014715254,
    0.04398934,
    0.008029662,
    0.350316246,
]
PAIR_RANK_STDS = [
    1.0,
    0.1842578,
    0.284562508,
    0.284562508,
    0.18579725,
    0.156486205,
    0.419879383,
    0.284549925,
    0.157152553,
    0.429517446,
    0.438372073,
    0.419188739,
    0.421646414,
    0.470477449,
    0.461815853,
    0.162022928,
    0.322434624,
    0.173772993,
    0.335209224,
    0.120410611,
    0.205071398,
    0.089247895,
    0.246820134,
]

CLUSTER_EDGE_THRESHOLD = 1.50
CLUSTER_MERGE_MEAN_THRESHOLD = 0.60
CLUSTER_MERGE_MIN_THRESHOLD = -1.25
MAX_CLUSTER_SIZE = 18
MAX_TOKEN_BLOCK = 500
WEAK_CLUSTER_SPLIT_THRESHOLD = 0.0
WEAK_CLUSTER_SPLIT_MIN_SIZE = 10
WEAK_CLUSTER_SPLIT_SIZE_STEP = 1.2
STRONG_SPLIT_KEEP_THRESHOLD = 5.0
POST_REMERGE_GRAPH_MEAN_THRESHOLD = 2.0
POST_REMERGE_RANK_MEAN_THRESHOLD = 4.0
POST_REMERGE_RANK_MIN_THRESHOLD = 0.0
GLOBAL_REMERGE_GRAPH_MEAN_THRESHOLD = 0.0
GLOBAL_REMERGE_RANK_MEAN_THRESHOLD = 2.0
GLOBAL_REMERGE_RANK_MIN_THRESHOLD = -1.0
GLOBAL_REMERGE_MAX_TOKEN_BLOCK = 80
LEARNED_CLUSTER_BLEND = 0.20
LEARNED_CLUSTER_INTERCEPT = 1.740513695861389
LEARNED_CLUSTER_WEIGHTS = [
    0.0,
    0.7773663292008067,
    2.7266379662775067,
    2.7266379662775067,
    1.804590941687611,
    -7.745422981742341,
    0.4581146628756747,
    0.15665768756493506,
    -0.38673719323852684,
    -0.8247973269449391,
    -2.103346211421149,
    0.16759502715906147,
    -4.045883244617306,
    -0.9603906992896433,
    -10.10149880773338,
    -0.6606873781080495,
    -0.18017163524897037,
    -0.9084545727939811,
    -0.5422719125486231,
    -0.5422719125486231,
    -0.6451095436357495,
    -2.227615286724915,
    0.21628173755444968,
    -1.6081726231546238,
    3.813599491028173,
    2.1449647504564204,
    -1.4011194153639264,
    0.5561460047924002,
    0.5668335665068689,
    0.24164821658486096,
    -0.34023044707974265,
    2.813024763468897,
    0.8927370247986126,
    9.764290571489031,
]
LEARNED_CATEGORY_MODELS = {
    "arbeitsspeicher": (
        2.7246380830157175,
        [
            0.0,
            -8.969045251136315,
            3.1740690925094004,
            3.1740690925094004,
            -3.0337082442544743,
            -6.254788773457518,
            -0.23438109145393857,
            -0.5533372642607514,
            -1.772959829492671,
            1.4914810656150246,
            -4.221447570044783,
            0.5162993133634876,
            -2.217500731065869,
            0.0,
            -9.811119098920631,
            -1.8950247256601203,
            -1.5069135120826318,
            -2.6172323341927286,
            2.9149577375321503,
            2.9149577375321503,
            3.968577851703104,
            -3.607599288891439,
            4.0214353132244485,
            0.8706728845960237,
            1.4662102869057678,
            3.0269913381603786,
            -1.31665111811639,
            1.4959846517456115,
            0.6269652439411076,
            -0.44514846760479676,
            0.6732830002605845,
            -0.16738592630823923,
            -4.515509449207692,
            4.7313357948120505,
        ],
    ),
    "fernseher": (
        2.7755886134986465,
        [
            0.0,
            -1.6955346984730693,
            -3.6499900678184076,
            -3.6499900678184076,
            6.430691838280349,
            2.8966717654861482,
            -0.5492532620948394,
            -1.2338260346017074,
            7.0031706538956096,
            -0.9800862734689273,
            -1.0733791785185351,
            0.01124078488683349,
            0.0,
            -2.766832525000881,
            -5.417095576770249,
            -3.225146712207468,
            -0.7533153972043938,
            9.655209070564231,
            -0.7315736056518515,
            -0.7315736056518515,
            -5.283576519239036,
            -0.7987836414166456,
            2.7864147888083144,
            3.344693468190731,
            -1.0171233631437462,
            -5.409244707112693,
            -0.8671508397839481,
            -0.09059297268354982,
            1.0208343620439926,
            -0.18763097955336955,
            0.8995048325587086,
            -0.12631470225707475,
            3.756687203922055,
            -6.0296039471472636,
        ],
    ),
    "grafikkarten": (
        2.4485174694185456,
        [
            0.0,
            8.122975230834648,
            0.37780149998202706,
            0.37780149998202706,
            -8.526545252454167,
            -5.052359875854728,
            -0.7161631324927507,
            3.008367202276972,
            -5.5040219884148085,
            -1.5768929481901832,
            0.3493746881968843,
            0.0,
            -5.183642936885311,
            -2.424004216455795,
            -10.104435972847288,
            0.19918070270520014,
            -8.50857367451013,
            -4.287297949538745,
            6.667602546270311,
            6.667602546270311,
            0.6584041448750555,
            -1.4540450609485125,
            4.942927125464076,
            -3.2974086271180596,
            -1.3275408803612492,
            -3.5381749414748676,
            -3.1928835759782133,
            0.7728957696729049,
            2.1447813323712244,
            -2.6731294251292868,
            7.334233446284037,
            -0.8366147360467654,
            -0.29638728236944145,
            2.777472842109723,
        ],
    ),
    "handys ohne vertrag": (
        0.9702181556618346,
        [
            0.0,
            12.894228215871884,
            2.8608386927671656,
            2.8608386927671656,
            9.042023448756758,
            -1.4911863171538147,
            0.25794014011932703,
            -0.47122711387739,
            1.1329835458054742,
            0.8323122338934765,
            -2.3902112559991124,
            1.40850578405331,
            -8.127983563601118,
            -0.6983488380143807,
            -7.9708714289381675,
            5.117566503496583,
            -10.961122787016476,
            6.915311117876873,
            -6.293226937294032,
            -6.293226937294032,
            1.6760830348245916,
            -14.555495867993313,
            6.2765920623790965,
            -2.5885857646293293,
            2.2917489720856197,
            4.486512303919225,
            -1.9074900338677616,
            -0.0006261049130339364,
            0.8119737003938036,
            0.1872187903766215,
            0.47473909698914524,
            2.13843114879603,
            -4.774100832507037,
            0.1766170763125162,
        ],
    ),
    "notebooks": (
        0.312075258032003,
        [
            0.0,
            21.376579281251782,
            2.855623150893292,
            2.855623150893292,
            3.148259037337436,
            -5.604509669012247,
            0.18233608820984742,
            0.23982897056223842,
            -0.46345494544760696,
            -0.9798589160530401,
            -1.5081536193794707,
            1.3703527025548512,
            -6.965616557725054,
            -0.24451102914236483,
            -15.48394502326097,
            1.2991573415798843,
            -22.668634274870588,
            7.0874671351517025,
            -2.522274596494691,
            -2.522274596494691,
            0.7237425045642696,
            -9.215852997384737,
            3.6961299656219864,
            -9.300789572642149,
            6.68255203124291,
            6.625250878962781,
            -1.7671870533142264,
            0.36091966068601755,
            2.308594355990452,
            -0.020119355455552414,
            0.3264593856044362,
            5.669343575322058,
            0.26848900624104394,
            7.696418336701239,
        ],
    ),
    "smartwatches": (
        1.9376934079852806,
        [
            0.0,
            -0.7825194361564983,
            1.1695810181305593,
            1.1695810181305593,
            -0.1685191626563587,
            -1.701132975304161,
            -0.30784576970838284,
            -0.5259165802897025,
            -2.1661824667927836,
            -0.39509348408048006,
            -1.1232704006124032,
            -1.1453741047119592,
            0.0,
            -1.620256276545131,
            -13.548244866716752,
            -2.5803994000416286,
            0.9100474968579988,
            -2.1297113064918074,
            -0.4653871551990806,
            -0.4653871551990806,
            -0.5998590316022486,
            2.9315841979690007,
            -0.6143693994071724,
            -11.817890574915904,
            10.401089695928794,
            8.953681018446247,
            -0.6112438823606682,
            -0.27206792214789777,
            0.23450924820395957,
            -0.43625369876671904,
            1.374264854950402,
            7.815527867156294,
            3.5674976962012717,
            -1.0267237658161037,
        ],
    ),
    "tablet pcs": (
        2.3107291838362585,
        [
            0.0,
            -1.6789491401118806,
            1.7854337267977693,
            1.7854337267977693,
            -1.7096036867396383,
            1.2878348200805536,
            -0.155857842860622,
            -0.9286332838243094,
            1.6219236321777748,
            -0.29437946750658484,
            -2.398837533678742,
            1.6752883585346305,
            -6.906772524496085,
            0.5587396061682025,
            -7.767375227247435,
            -0.9777339485505857,
            0.8767314229159519,
            -1.3028651508187905,
            2.2953150018967,
            2.2953150018967,
            -2.5468571407367713,
            -2.415181383110831,
            1.2703063682673124,
            -0.07139417143336618,
            -0.4013943240573565,
            0.9737212740348238,
            -1.6287567674798913,
            -2.176700851324929,
            3.2835951186637438,
            -0.10764394494527266,
            0.9520983085632932,
            2.3826880612409322,
            -0.6760953003847375,
            2.1818189004284827,
        ],
    ),
}

CAPACITY_AS_PRODUCT_CATEGORIES = {
    "arbeitsspeicher",
    "grafikkarten",
}
STORAGE_HARD_CONFLICT_CATEGORIES = {
    "handys ohne vertrag",
    "notebooks",
    "tablet pcs",
}
COLOR_HARD_CONFLICT_CATEGORIES = {
    "arbeitsspeicher",
    "grafikkarten",
}
SIZE_HARD_CONFLICT_CATEGORIES = {
    "e-bikes",
}
GLOBAL_REMERGE_GENERIC_CODES = {
    "galaxys25",
    "m5",
    "rx9070",
    "rtx5060",
    "rtx5070",
    "s25",
}
GLOBAL_REMERGE_GENERIC_PREFIXES = (
    "ddr",
    "gddr",
    "ramcl_",
    "ramform_",
    "rammodules_",
    "ramspd_",
)
LONG_PREFIX_CODE_CATEGORIES = {
    "navigationssysteme",
    "smartwatches",
}
ONE_DIGIT_CODE_CATEGORIES = {
    "gaming-zubehör",
    "handys ohne vertrag",
    "konsolen",
    "kopfhörer",
    "monitore",
    "multifunktionsdrucker",
    "smartwatches",
    "tablet pcs",
}
ADJACENT_CODE_PREFIX_STOPWORDS = {
    "cm",
    "core",
    "galaxy",
    "gb",
    "gen",
    "hz",
    "iphone",
    "mah",
    "mm",
    "model",
    "modell",
    "pixel",
    "poco",
    "redmi",
    "series",
    "tab",
    "w",
    "watch",
    "wh",
    "wifi",
    "wlan",
}

BASE_STOPWORDS = {
    "und",
    "mit",
    "ohne",
    "fuer",
    "für",
    "der",
    "die",
    "das",
    "den",
    "dem",
    "des",
    "ein",
    "eine",
    "einer",
    "einem",
    "einen",
    "neu",
    "new",
    "smart",
    "top",
    "deal",
    "topseller",
    "display",
    "oled",
    "amoled",
    "led",
    "serie",
    "series",
    "modell",
    "model",
    "generation",
    "gen",
    "laptop",
    "notebook",
    "tablet",
    "smartphone",
    "handy",
    "pc",
    "wlan",
    "wifi",
    "bluetooth",
    "windows",
    "win",
    "android",
    "dual",
    "sim",
    "free",
    "inkl",
    "inklusiv",
    "cm",
    "mm",
    "zoll",
    "inch",
    "gb",
    "tb",
    "ram",
    "ssd",
    "hdd",
    "core",
    "intel",
    "amd",
    "nvidia",
    "geforce",
    "rtx",
    "radeon",
}

COLOR_ALIASES = {
    "schwarz": "black",
    "black": "black",
    "noir": "black",
    "onyx": "black",
    "midnight": "black",
    "titanblack": "black",
    "titanschwarz": "black",
    "diamantschwarz": "black",
    "graphitschwarz": "black",
    "jet": "black",
    "jetblack": "black",
    "mitternacht": "black",
    "weiss": "white",
    "weiß": "white",
    "white": "white",
    "snow": "white",
    "starlight": "white",
    "polarstern": "white",
    "steinweiss": "white",
    "whitestone": "white",
    "silber": "silver",
    "silver": "silver",
    "edelstahl": "silver",
    "platinum": "silver",
    "platin": "silver",
    "grau": "gray",
    "gray": "gray",
    "grey": "gray",
    "graphite": "gray",
    "graphit": "gray",
    "anthrazit": "gray",
    "carbongrau": "gray",
    "schiefer": "gray",
    "schiefergrau": "gray",
    "space": "gray",
    "spacegrau": "gray",
    "spacegray": "gray",
    "spacegrey": "gray",
    "titan": "gray",
    "titanfarben": "gray",
    "titanium": "gray",
    "gruen": "green",
    "grün": "green",
    "green": "green",
    "sage": "green",
    "salbei": "green",
    "mint": "green",
    "jade": "green",
    "jadegreen": "green",
    "jadesgruen": "green",
    "jadesgrün": "green",
    "mintgruen": "green",
    "moosgruen": "green",
    "moosgrün": "green",
    "lila": "purple",
    "violett": "purple",
    "violet": "purple",
    "purple": "purple",
    "lavender": "purple",
    "lavenderblue": "purple",
    "lavendel": "purple",
    "iris": "purple",
    "nebelviolett": "purple",
    "pflaume": "purple",
    "purplefog": "purple",
    "sparkling": "purple",
    "grape": "purple",
    "blau": "blue",
    "blue": "blue",
    "navy": "blue",
    "icyblue": "blue",
    "hellblau": "blue",
    "himmelblau": "blue",
    "silverblue": "blue",
    "skyblau": "blue",
    "skyblue": "blue",
    "cloud": "blue",
    "blaugruen": "teal",
    "blaugrün": "teal",
    "teal": "teal",
    "tuerkis": "teal",
    "turkis": "teal",
    "türkis": "teal",
    "rot": "red",
    "red": "red",
    "rosa": "pink",
    "pink": "pink",
    "pinkgold": "pink",
    "blassrosa": "pink",
    "blush": "pink",
    "hellrosa": "pink",
    "orange": "orange",
    "gold": "gold",
    "softgold": "gold",
    "rose": "gold",
    "rosegold": "gold",
    "beige": "beige",
    "cream": "beige",
    "creme": "beige",
    "natur": "beige",
    "sand": "beige",
    "sandstorm": "beige",
    "sandsturm": "beige",
    "gelb": "yellow",
    "yellow": "yellow",
    "braun": "brown",
    "brown": "brown",
    "champagner": "gold",
    "champagne": "gold",
}


@dataclass(frozen=True)
class Offer:
    offer_id: str
    title: str
    shop: str
    brand: str
    category: str
    price: float
    normalized: str
    compact: str
    content: frozenset[str]
    codes: frozenset[str]
    units: frozenset[str]
    storages: frozenset[str]
    connectivity: frozenset[str]
    editions: frozenset[str]
    colors: frozenset[str]
    sizes: frozenset[str]
    numbers: frozenset[str]
    ram_speeds: frozenset[str]
    ram_layouts: frozenset[str]
    ram_forms: frozenset[str]
    ram_latencies: frozenset[str]
    variant_signals: frozenset[str]
    cluster_content: frozenset[str]
    cluster_codes: frozenset[str]
    cluster_variant_signals: frozenset[str]
    content_weight: float = 1.0
    cluster_content_weight: float = 1.0


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", text.casefold())
    value = (
        value.replace("ß", "ss")
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
    )
    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        character for character in value if not unicodedata.combining(character)
    )
    value = re.sub(r'(\d+)[,.](\d+)\s*("|zoll|inch)', r"\1_\2zoll", value)
    value = re.sub(
        r"(\d+)\s*(tb|tbyte|terabyte)\b",
        lambda match: f"{int(match.group(1)) * 1024}gb",
        value,
    )
    value = re.sub(r"(\d+)\s*(gb|gbyte|gigabyte)\b", r"\1gb", value)
    value = re.sub(r"(\d+)[,.](\d+)\s*(cm|mm)", r"\1_\2\3", value)
    value = re.sub(r"(\d+)\s*(mah|hz|wh|w|mm|cm)\b", r"\1\2", value)
    value = value.replace('"', " zoll ")
    value = re.sub(r"[^a-z0-9_]+", " ", value)
    return " ".join(value.split())


def _parse_price(raw: str) -> float:
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _infer_category(normalized: str, brand: str) -> str:
    compact = normalized.replace(" ", "")
    looks_tablet = bool(
        re.search(
            r"\bipad\b|\bgalaxy\s+tab\b|\btab\s+[as]\b|\btablet\b|"
            r"\bredmi\s+pad\b|\bxiaomi\s+pad\b|\bidea\s+tab\b|\byoga\s+tab\b|"
            r"\bsurface\s+pro\b",
            normalized,
        )
    )
    looks_notebook = bool(
        re.search(
            r"\bnotebook\b|\blaptop\b|\bmacbook\b|\bthinkpad\b|\bgalaxy\s+book\b|"
            r"\bgalaxy\s+book[0-9]\b|\bomnibook\b|\baspire\b|"
            r"\bsurface\s+laptop\b|\bexpertbook\b|\bvivobook\b|\bzenbook\b|"
            r"\bideapad\b|\byoga\b|\bprobook\b|\belitebook\b|\bchromebook\b|"
            r"\bthinkbook\b|\bnitro\s+v\b|\bvector\s+[0-9]|\btuf\s+gaming\b",
            normalized,
        )
        or (
            re.search(r"\bwin(?:dows)?\s*11\b|\bcopilot\b", normalized)
            and re.search(r"\bcore\s+ultra\b|\bryzen\b|\brtx\b", normalized)
        )
    )
    if re.search(
        r"\bmaehroboter\b|\brasenmaehroboter\b|\brasenroboter\b|"
        r"\broboter\s+rasenmaeher\b|\bindego\b",
        normalized,
    ):
        return "mähroboter"
    if brand == "dji" and re.search(r"\bmic\s*[0-9]\b|\bmikrofon\b|\bmicrophone\b", normalized):
        return "mikrofone"
    if brand == "dji" and re.search(r"\bavata\b|\bdrohne\b|\bdrone\b|\bdji\s+mini\b|\bmavic\b", normalized):
        return "drohnen"
    if looks_tablet:
        return "tablet pcs"
    if re.search(
        r"\bapple\s+watch\b|\bgalaxy\s+watch\b|\bsmartwatch\b|\bsportuhr\b|"
        r"\bvenu\b|\bfenix\b|\bforerunner\b|\binstinct\b|\bamazfit\b|"
        r"\bbalance\b|\bwatch\s+(?:se|ultra|[0-9])\b|\bwatch\s+fit\b|"
        r"\bwatch[0-9]\b|\bfitness\s+tracker\b|\bactivity\s+tracker\b|"
        r"\bscanwatch\b|\bwatch\s+gt\s*[0-9]\b|"
        r"\b(?:sm[-\s]*)?l\s*(?:330|705)\b",
        normalized,
    ) or (
        brand in {"fitbit", "withings"}
        and re.search(r"\bcharge\b|\bsense\b|\bscanwatch\b", normalized)
    ) or (brand == "huawei" and re.search(r"\bgt\s*[0-9]\b", normalized)):
        return "smartwatches"
    if re.search(
        r"\biphone\b|\bsmartphone\b|\bhandy\b|\bmobiltelefon\b|\bgalaxy\s+s\b|"
        r"\bsm\s*s[0-9]|\bs[0-9]{2}\s*(?:ultra|plus|fe)?\b|"
        r"\bedge\s*[0-9]{2}\b|\brazr\s*[0-9]{2}\b|\bmoto\s*g\s*[0-9]{2}\b|"
        r"\bpoco\b|\bredmi\s+note\b",
        normalized,
    ):
        return "handys ohne vertrag"
    if brand == "google" and re.search(r"\bpixel\s*[0-9]{1,2}[a-z]?\b", normalized):
        return "handys ohne vertrag"
    if brand in {"oneplus", "honor", "motorola", "oppo", "realme", "nothing"} and re.search(
        r"\b[0-9]{1,3}[a-z]?\b.*\b(?:gb|5g|dual\s*sim)\b",
        normalized,
    ):
        return "handys ohne vertrag"
    if brand in {"oneplus", "honor", "motorola", "oppo", "realme", "nothing"} and re.search(
        r"\b(?:gb|5g|dual\s*sim)\b",
        normalized,
    ):
        return "handys ohne vertrag"
    if brand == "xiaomi" and re.search(
        r"\b(?:xiaomi\s*)?[0-9]{1,2}[a-z]?\b|\bredmi\b|\bpoco\b",
        normalized,
    ):
        return "handys ohne vertrag"

    if looks_notebook:
        return "notebooks"

    if re.search(
        r"\brtx\b|\brtx[0-9]{4}(?:ti)?\b|\bgeforce\b|\bradeon\b|"
        r"\brx\s*[0-9]{4}(?:\s*xt)?\b|\brx[0-9]{4}(?:xt)?\b",
        normalized,
    ):
        return "grafikkarten"

    if re.search(
        r"\bmonitor\b|\bodyssey\b|\bcurved\b|\bdisplayport\b|\bstudio\s+display\b|"
        r"\bcomputerbildschirm\b|\bviewfinity\b|\bevnia\b|\brog\s+strix\s+xg",
        normalized,
    ):
        return "monitore"
    if re.search(
        r"\bfernseher\b|\bsmart\s*tv\b|\btv\b|\bambilight\b|\bqled\b|"
        r"\bneo\s+qled\b|\b[0-9]{2}oled[0-9]|\bgq[0-9]{2}",
        normalized,
    ):
        return "fernseher"

    if re.search(
        r"\bddr[345]\b|\bsodimm\b|\bso\s*dimm\b|\bdimm\b|\barbeitsspeicher\b",
        normalized,
    ):
        return "arbeitsspeicher"
    if re.search(r"\bssd\b|\bnvme\b|\bm\s*2\b|\bpcie\b", normalized):
        return "ssd festplatten"

    if re.search(r"\bairpods\b|\bbuds\b|\bkopfhoerer\b|\bkopfhorer\b|\bheadphones\b", normalized):
        return "kopfhörer"
    if re.search(r"\bsonicare\b|\bzahnbuerste\b|\bhx\s*[0-9]{4}\b|\bio\s+series\b", normalized):
        return "elektrische zahnbürsten"
    if re.search(r"\bkaffeevollautomat\b|\becam\b", normalized):
        return "kaffeevollautomaten"
    if re.search(
        r"\bespressomaschine\b|\bdedica\b|\bsiebtraeger\b|"
        r"\bsiebtraegermaschine\b|\bbarista\b",
        normalized,
    ):
        return "espressomaschinen"
    if re.search(r"\bheissluftfritteuse\b|\bairfryer\b|\bcrisp[iy]\b", normalized):
        return "fritteusen"
    if re.search(r"\bgoat\b", normalized):
        return "mähroboter"
    if re.search(r"\be[-\s]?bike\b|\bkathmandu\b|\btrekking\b|\bhybrid\b", normalized):
        return "e-bikes"
    if re.search(r"\bdrohne\b|\bdrone\b|\bdji\s+mini\b|\bmavic\b", normalized):
        return "drohnen"
    if re.search(r"\bmikrofon\b|\bmicrophone\b|\bdji\s+mic\b", normalized):
        return "mikrofone"
    if re.search(r"\bnavigationsgeraet\b|\bnavigation\b|\bdrivesmart\b|\bcamper\b", normalized):
        return "navigationssysteme"
    if re.search(
        r"\bsystemkamera\b|\bnikon\s+z\b|\bsony\s+alpha\b|\bcanon\s+eos\b|"
        r"\bfujifilm\s+x[-\s]*[a-z0-9]|\bom\s+system\s+om",
        normalized,
    ):
        return "systemkameras"
    if re.search(r"\bkompaktkamera\b|\bcyber\s*shot\b|\brx\s*100\b", normalized):
        return "kompaktkameras"
    if re.search(r"\brouter\b|\bfritz\s*box\b|\bwifi\s*[67]\b|\bwlan\s*router\b", normalized):
        return "router"
    if re.search(r"\bsaugroboter\b|\broborock\b|\broomba\b", normalized):
        return "saugroboter"
    if re.search(r"\bstaubsauger\b|\bdyson\b", normalized):
        return "staubsauger"
    if re.search(r"\bfritteuse\b|\bairfryer\b", normalized):
        return "fritteusen"
    if re.search(r"\bkuechenmaschine\b|\bthermomix\b|\bkitchenaid\b", normalized):
        return "küchenmaschinen"
    if "galaxybook" in compact:
        return "notebooks"
    return "generic"


def _extract_ram_specs(
    raw_normalized: str,
) -> tuple[set[str], set[str], set[str], set[str]]:
    speeds: set[str] = set()
    layouts: set[str] = set()
    forms: set[str] = set()
    latencies: set[str] = set()

    for pattern in [
        r"\bddr[45][-\s]*([4-8][0-9]{3})\b",
        r"\b([4-8][0-9]{3})\s*(?:mhz|mt\s*/\s*s)\b",
        r"\bpc\s*([4-8][0-9]{3})\b",
    ]:
        for match in re.finditer(pattern, raw_normalized):
            speed = int(match.group(1))
            if 4800 <= speed <= 8400:
                speeds.add(f"ramspd_{speed}")
    for match in re.finditer(
        r"\b([4-8])[,.]000\s*(?:mhz|mt\s*/\s*s)\b",
        raw_normalized,
    ):
        speeds.add(f"ramspd_{match.group(1)}000")

    for match in re.finditer(
        r"\b([1-8])\s*x\s*([0-9]{1,3})\s*gb\b",
        raw_normalized,
    ):
        layouts.add(f"ramkit_{match.group(1)}x{match.group(2)}gb")
        layouts.add(f"rammodules_{match.group(1)}")
    for match in re.finditer(
        r"\b[0-9]{1,4}\s*gb\s*:\s*([1-8])\s*x\s*([0-9]{1,3})\b",
        raw_normalized,
    ):
        layouts.add(f"ramkit_{match.group(1)}x{match.group(2)}gb")
        layouts.add(f"rammodules_{match.group(1)}")
    for match in re.finditer(r"\bkit\s+of\s+([1-8])\b", raw_normalized):
        layouts.add(f"rammodules_{match.group(1)}")
    for match in re.finditer(r"\b([1-8])er[-\s]*kit\b", raw_normalized):
        layouts.add(f"rammodules_{match.group(1)}")
    for match in re.finditer(r"\b([1-8])\s*pcs\b", raw_normalized):
        layouts.add(f"rammodules_{match.group(1)}")
    if re.search(r"\bsingle\s+channel\b", raw_normalized):
        layouts.add("rammodules_1")
    if re.search(r"\bdual\s+channel\b", raw_normalized):
        layouts.add("rammodules_2")

    if re.search(r"\bso[-\s]*dimm\b|\bsodimm\b", raw_normalized):
        forms.add("ramform_sodimm")
    elif re.search(r"\bu[-\s]*dimm\b|\budimm\b|\bdimm\b", raw_normalized):
        forms.add("ramform_dimm")

    for match in re.finditer(r"\bcl\s*([0-9]{2})\b", raw_normalized):
        latency = int(match.group(1))
        if 20 <= latency <= 60:
            latencies.add(f"ramcl_{latency}")

    return speeds, layouts, forms, latencies


def _canonical_storage_capacity(capacity: int) -> int:
    for decimal, binary in [
        (1000, 1024),
        (2000, 2048),
        (4000, 4096),
        (5000, 5120),
        (8000, 8192),
        (10000, 10240),
    ]:
        if decimal - 50 <= capacity <= decimal + 50:
            return binary
    return capacity


def _extract_watch_signals(
    *,
    brand: str,
    normalized: str,
) -> tuple[set[str], set[str], set[str], set[str]]:
    content: set[str] = set()
    codes: set[str] = set()
    sizes: set[str] = set()
    connectivity: set[str] = set()

    if brand == "apple":
        series_match = re.search(r"\bwatch\s+(?:series\s+)?([0-9]{1,2})\b", normalized)
        if series_match:
            generation = series_match.group(1)
            content.add(f"watchmodel:apple_series_{generation}")
            codes.add(f"applewatchseries{generation}")
        shorthand_series_match = re.search(
            r"\bwatch\s+s\s*([0-9]{1,2})\b|\bs\s*([0-9]{1,2})\b",
            normalized,
        )
        if shorthand_series_match:
            generation = (
                shorthand_series_match.group(1)
                or shorthand_series_match.group(2)
            )
            content.add(f"watchmodel:apple_series_{generation}")
            codes.add(f"applewatchseries{generation}")
        se_match = re.search(r"\bwatch\s+se\s*([0-9])\b|\bse\s*([0-9])\b", normalized)
        if se_match:
            generation = se_match.group(1) or se_match.group(2)
            content.add(f"watchmodel:apple_se_{generation}")
            codes.add(f"applewatchse{generation}")
        ultra_match = re.search(r"\bwatch\s+ultra\s*([0-9])?\b", normalized)
        if ultra_match:
            generation = ultra_match.group(1)
            content.add("watchmodel:apple_ultra")
            codes.add("applewatchultra")
            if generation:
                content.add(f"watchmodel:apple_ultra_{generation}")
                codes.add(f"applewatchultra{generation}")
    elif brand == "samsung":
        if "galaxy watch ultra" in normalized or re.search(
            r"\bwatch\s+ultra\b",
            normalized,
        ):
            content.add("watchmodel:samsung_ultra")
            codes.add("galaxywatchultra")
        for sku, model in [
            ("l705", "samsung_ultra_2025"),
            ("l330", "samsung_watch8_44_bt"),
        ]:
            if re.search(rf"\b(?:sm[-\s]*)?{sku[0]}\s*{sku[1:]}\b", normalized):
                content.add(f"watchmodel:{model}")
                codes.add(model.replace("_", ""))
        model_match = re.search(
            r"\bgalaxy\s+watch\s*([0-9])\b|\bwatch\s*([0-9])\b|\bwatch([0-9])\b",
            normalized,
        )
        if model_match:
            generation = (
                model_match.group(1)
                or model_match.group(2)
                or model_match.group(3)
            )
            content.add(f"watchmodel:samsung_{generation}")
            codes.add(f"galaxywatch{generation}")
    elif brand == "huawei":
        gt_match = re.search(r"\bwatch\s+gt\s*([0-9])\b|\bgt\s*([0-9])\b", normalized)
        if gt_match:
            generation = gt_match.group(1) or gt_match.group(2)
            content.add(f"watchmodel:huawei_gt_{generation}")
            codes.add(f"huaweiwatchgt{generation}")
        model_match = re.search(r"\bwatch\s*([0-9])\b", normalized)
        if model_match:
            generation = model_match.group(1)
            content.add(f"watchmodel:huawei_{generation}")
            codes.add(f"huaweiwatch{generation}")
    elif brand == "garmin":
        for prefix in ["fenix", "venu", "forerunner", "instinct", "vivoactive"]:
            model_match = re.search(rf"\b{prefix}\s*([0-9]{{1,3}})\b", normalized)
            if model_match:
                generation = model_match.group(1)
                content.add(f"watchmodel:{prefix}_{generation}")
                codes.add(f"{prefix}{generation}")

    for size_match in re.finditer(r"\b(40|41|42|44|45|46|47|49)\s*mm\b", normalized):
        case_size = f"watchcase_{size_match.group(1)}mm"
        content.add(case_size)
        sizes.add(case_size)
    if re.search(r"\bgps\b", normalized):
        connectivity.add("gps")
    if re.search(r"\blte\b|\besim\b|\b4g\b|\bcellular\b", normalized):
        connectivity.add("lte")

    return content, codes, sizes, connectivity


def _extract_tablet_phone_audio_aliases(
    offer: Offer,
) -> tuple[set[str], set[str]]:
    content: set[str] = set()
    codes: set[str] = set()
    normalized = offer.normalized
    raw_normalized = unicodedata.normalize("NFKC", offer.title.casefold()).replace(
        "ß",
        "ss",
    )

    if offer.category == "tablet pcs":
        if offer.brand == "samsung":
            model_match = re.search(
                r"\b(?:galaxy\s+)?tab\s+s\s*([0-9]{1,2})\s*(fe)?\s*(?:\+|plus)?\b",
                normalized,
            )
            if model_match:
                generation = model_match.group(1)
                has_fe = bool(model_match.group(2))
                has_plus = bool(
                    re.search(
                        rf"\btab\s+s\s*{re.escape(generation)}\s*(?:fe\s*)?(?:\+|plus)",
                        raw_normalized,
                    )
                )
                if has_fe and has_plus and re.search(
                    r"\bx\s*520\b|\b10_?9(?:0)?zoll\b|\b10\s*9\b|\b10\s*90\b",
                    normalized,
                ):
                    has_plus = False
                suffix = (
                    "feplus"
                    if has_fe and has_plus
                    else "fe"
                    if has_fe
                    else "plus"
                    if has_plus
                    else ""
                )
                content.add(f"tabmodel:samsung_s{generation}{suffix}")
                codes.add(f"galaxytabs{generation}{suffix}")
            for model_code in re.finditer(
                r"\bsm[-\s]*x\s*([0-9]{3})([a-z]{0,4})\b|\bx\s*([0-9]{3})([a-z]{0,4})\b",
                normalized,
            ):
                number = model_code.group(1) or model_code.group(3)
                suffix = model_code.group(2) or model_code.group(4) or ""
                if number:
                    codes.add(f"smx{number}{suffix}")
                    content.add(f"smx{number}")
        elif offer.brand == "apple":
            family_match = re.search(r"\bipad\s+(air|pro|mini)\b", normalized)
            if family_match:
                family = family_match.group(1)
                content.add(f"ipadfamily:{family}")
                codes.add(f"ipad{family}")
                size_match = re.search(
                    r"\b(11|13)\s*(?:inch|zoll)?\b|\b(11|13)_\d+zoll\b",
                    normalized,
                )
                if size_match:
                    size = size_match.group(1) or size_match.group(2)
                    content.add(f"ipadmodel:{family}_{size}")
                    codes.add(f"ipad{family}{size}")

    if offer.category == "handys ohne vertrag":
        if offer.brand == "apple":
            iphone_match = re.search(
                r"\biphone\s*([0-9]{1,2})(?:\s*(pro\s*max|pro|max|plus|air|mini|e))?\b",
                normalized,
            )
            if iphone_match:
                suffix = (iphone_match.group(2) or "").replace(" ", "")
                model = f"iphone{iphone_match.group(1)}{suffix}"
                content.add(f"phonemodel:{model}")
                codes.add(model)
        elif offer.brand == "google":
            model_match = re.search(r"\bpixel\s*([0-9]{1,2})\s*([a-z])?\b", normalized)
            if model_match:
                model = f"pixel{model_match.group(1)}{model_match.group(2) or ''}"
                content.add(f"phonemodel:{model}")
                codes.add(model)
        elif offer.brand == "samsung":
            model_match = re.search(r"\b(?:galaxy\s+)?s\s*([0-9]{2})\b", normalized)
            if model_match:
                generation = model_match.group(1)
                suffix = ""
                if re.search(
                    rf"\b(?:galaxy\s+)?s\s*{re.escape(generation)}\s*(?:\+|plus)\b",
                    raw_normalized,
                ):
                    suffix = "plus"
                else:
                    suffix_match = re.search(
                        rf"\b(?:galaxy\s+)?s\s*{re.escape(generation)}\s*(ultra|fe)\b",
                        normalized,
                    )
                    suffix = suffix_match.group(1) if suffix_match else ""
                model = f"galaxys{generation}{suffix}"
                content.add(f"phonemodel:{model}")
                codes.add(model)
        elif offer.brand == "xiaomi":
            model_match = re.search(
                r"\b(?:redmi\s+)?note\s*([0-9]{1,2})(?:\s*(pro))?(?:\s*(?:\+|plus))?\b",
                normalized,
            )
            if model_match:
                has_plus = bool(
                    re.search(
                        rf"\bnote\s*{re.escape(model_match.group(1))}(?:\s*pro)?\s*(?:\+|plus)\b",
                        normalized,
                    )
                )
                suffix = f"{model_match.group(2) or ''}{'plus' if has_plus else ''}"
                model = f"redminote{model_match.group(1)}{suffix}"
                content.add(f"phonemodel:{model}")
                codes.add(model)
            redmi_match = re.search(
                r"\bredmi\s+(?!note\b)([0-9]{1,2}[a-z]?)(?:\s*(pro|plus|ultra))?\b",
                normalized,
            )
            if redmi_match:
                suffix = redmi_match.group(2) or ""
                model = f"redmi{redmi_match.group(1)}{suffix}"
                content.add(f"phonemodel:{model}")
                codes.add(model)
            xiaomi_match = re.search(
                r"\bxiaomi\s+([0-9]{1,2}t)(?:\s*(pro|ultra))?\b",
                normalized,
            )
            if xiaomi_match:
                suffix = xiaomi_match.group(2) or ""
                model = f"xiaomi{xiaomi_match.group(1)}{suffix}"
                content.add(f"phonemodel:{model}")
                codes.add(model)
            poco_match = re.search(
                r"\bpoco\s*([a-z])\s*([0-9])(?:\s*(pro|ultra))?\b",
                normalized,
            )
            if poco_match:
                model = (
                    f"poco{poco_match.group(1)}"
                    f"{poco_match.group(2)}{poco_match.group(3) or ''}"
                )
                content.add(f"phonemodel:{model}")
                codes.add(model)
        elif offer.brand == "motorola":
            edge_match = re.search(
                r"\bedge\s*([0-9]{2})(?:\s*(fusion|neo|ultra|pro))?\b",
                normalized,
            )
            if edge_match:
                model = f"edge{edge_match.group(1)}{edge_match.group(2) or ''}"
                content.add(f"phonemodel:moto_{model}")
                codes.add(model)
            razr_match = re.search(
                r"\brazr\s*([0-9]{2})(?:\s*(ultra))?\b",
                normalized,
            )
            if razr_match:
                model = f"razr{razr_match.group(1)}{razr_match.group(2) or ''}"
                content.add(f"phonemodel:moto_{model}")
                codes.add(model)
            moto_g_match = re.search(r"\bmoto\s*g\s*([0-9]{2})\b", normalized)
            if moto_g_match:
                model = f"motog{moto_g_match.group(1)}"
                content.add(f"phonemodel:{model}")
                codes.add(model)

    if offer.category == "kopfhörer" and offer.brand == "samsung":
        model_match = re.search(
            r"\b(?:galaxy\s+)?buds\s*([0-9])\b|\br\s*([0-9]{3})\b|\bsm[-\s]*r\s*([0-9]{3})\b",
            normalized,
        )
        if model_match:
            model = model_match.group(1) or model_match.group(2) or model_match.group(3)
            if model == "540":
                model = "4"
            content.add(f"audiomodel:galaxybuds{model}")
            codes.add(f"galaxybuds{model}")

    return content, codes


def _extract_offer(row: dict[str, str], stopwords: set[str]) -> Offer:
    normalized = _normalize_text(row["title"])
    tokens = normalized.split()
    brand = row["brand"].casefold()
    category = _infer_category(normalized, brand)
    raw_normalized = unicodedata.normalize("NFKC", row["title"].casefold()).replace(
        "ß", "ss"
    )
    content: set[str] = set()
    codes: set[str] = set()
    units: set[str] = set()
    storages: set[str] = set()
    connectivity: set[str] = set()
    editions: set[str] = set()
    colors: set[str] = set()
    sizes: set[str] = set()
    numbers: set[str] = set()
    ram_speeds: set[str] = set()
    ram_layouts: set[str] = set()
    ram_forms: set[str] = set()
    ram_latencies: set[str] = set()
    variant_signals: set[str] = set()
    cluster_content: set[str] = set()
    cluster_codes: set[str] = set()
    cluster_variant_signals: set[str] = set()
    for token in tokens:
        color = COLOR_ALIASES.get(token)
        if color:
            colors.add(color)
        if token == "5g":
            connectivity.add("5g")
            if category in {"smartwatches", "tablet pcs"}:
                connectivity.add("lte")
        elif token in {"4g", "lte", "cellular"}:
            connectivity.add("lte")
        elif token in {"wifi", "wlan"}:
            connectivity.add("wifi")
        if token in {"ultra", "plus", "pro", "max", "mini", "fe", "se", "air"}:
            editions.add(token)
        if re.fullmatch(r"\d+(gb|mah|hz|wh|w|mm|cm)", token) or re.fullmatch(
            r"\d+_\d+(zoll|cm|mm)|\d+zoll", token
        ):
            units.add(token)
        if re.fullmatch(r"\d+gb", token):
            capacity = int(token[:-2])
            if capacity >= 64 or (
                category in CAPACITY_AS_PRODUCT_CATEGORIES and capacity >= 2
            ):
                storages.add(f"{_canonical_storage_capacity(capacity)}gb")
        if re.fullmatch(r"\d+(mm|cm)|\d+_\d+(zoll|cm|mm)|\d+zoll", token):
            sizes.add(token)
        if re.fullmatch(r"\d+", token) and 1 <= int(token) <= 999:
            numbers.add(token)
        if len(token) > 1 and token not in stopwords:
            if token.isdigit() and not (1 <= int(token) <= 999):
                continue
            content.add(color or token)
        if (
            len(token) >= 3
            and token not in {"5g", "4g", "3d", "2in1"}
            and any(character.isalpha() for character in token)
            and any(character.isdigit() for character in token)
            and not re.fullmatch(r"\d+(gb|mah|hz|wh|w|mm|cm|zoll)", token)
        ):
            codes.add(token.replace("_", ""))
    for left, right in zip(tokens, tokens[1:]):
        if (
            re.fullmatch(r"[a-z]{1,5}", left)
            and re.fullmatch(r"\d{2,5}[a-z]?|\d{1,2}_\d(zoll)?", right)
            and left not in ADJACENT_CODE_PREFIX_STOPWORDS
        ):
            code = f"{left}{right}".replace("_", "")
            if len(code) >= 3:
                codes.add(code)
        if re.fullmatch(r"[a-z]{1,4}\d{1,5}", left) and re.fullmatch(
            r"[a-z]{1,4}", right
        ):
            codes.add(f"{left}{right}")
        if (
            category in ONE_DIGIT_CODE_CATEGORIES
            and re.fullmatch(r"[a-z]{3,8}", left)
            and re.fullmatch(r"\d", right)
            and left not in ADJACENT_CODE_PREFIX_STOPWORDS
        ):
            codes.add(f"{left}{right}")
        if (
            category in LONG_PREFIX_CODE_CATEGORIES
            and re.fullmatch(r"[a-z]{6,12}", left)
            and re.fullmatch(r"\d{2,4}[a-z]?", right)
            and left not in ADJACENT_CODE_PREFIX_STOPWORDS
        ):
            codes.add(f"{left}{right}")
        if right == "plus" and re.fullmatch(r"[a-z]{0,5}\d{1,3}", left):
            code = f"{left}plus"
            codes.add(code)
            content.add(code)
        if left == "plus" and re.fullmatch(r"[a-z]{0,5}\d{1,3}", right):
            code = f"{right}plus"
            codes.add(code)
            content.add(code)
    if category == "smartwatches":
        if re.search(r"\bs\s*/\s*m\b|\bs-m\b|\bs\s+m\b", raw_normalized):
            sizes.add("band_sm")
            content.add("band_sm")
        if re.search(r"\bm\s*/\s*l\b|\bm-l\b|\bm\s+l\b", raw_normalized):
            sizes.add("band_ml")
            content.add("band_ml")
        shorthand_case_size = re.search(
            r"\b(40|41|42|44|45|46|47|49)\s*,\s*202[0-9]\b",
            raw_normalized,
        )
        if shorthand_case_size:
            case_size = f"watchcase_{shorthand_case_size.group(1)}mm"
            sizes.add(case_size)
            content.add(case_size)
        if brand == "apple":
            if re.search(r"\balpine\s+loop\b", raw_normalized):
                cluster_variant_signals.add("watchband:alpine")
            elif re.search(r"\b(?:milanese|milanaise)\b", raw_normalized):
                cluster_variant_signals.add("watchband:milanese")
            elif re.search(r"\bocean\s+(?:band|armband)\b", raw_normalized):
                cluster_variant_signals.add("watchband:ocean")
            elif re.search(r"\bsport(?:armband)?\b|\bsport\s+band\b", raw_normalized):
                cluster_variant_signals.add("watchband:sport")
        watch_content, watch_codes, watch_sizes, watch_connectivity = (
            _extract_watch_signals(brand=brand, normalized=normalized)
        )
        content.update(watch_content)
        codes.update(watch_codes)
        sizes.update(watch_sizes)
        connectivity.update(watch_connectivity)
        if brand == "apple":
            ultra_match = re.search(r"\bwatch\s+ultra\s*([0-9])\b", normalized)
            if ultra_match:
                variant_signals.add(f"watchmodel:apple_ultra_{ultra_match.group(1)}")
        elif brand == "samsung":
            if (
                re.search(r"\bwatch\s+ultra\b|galaxy\s+watch\s+ultra", normalized)
                and re.search(r"\b2025\b|\bl\s*705", normalized)
            ):
                cluster_content.add("watchmodel:samsung_ultra_2025")
                cluster_codes.add("samsungultra2025")
        elif brand == "garmin":
            fenix_match = re.search(r"\bfenix\s*([0-9])\b", normalized)
            if fenix_match:
                generation = fenix_match.group(1)
                if re.search(r"\bpro\b", normalized):
                    variant_signals.add(f"garminwatch:fenix{generation}pro")
                elif re.search(r"\bsapphire\b", normalized):
                    variant_signals.add(f"garminwatch:fenix{generation}sapphire")
                elif re.search(r"\bamoled\b", normalized):
                    variant_signals.add(f"garminwatch:fenix{generation}amoled")
            instinct_match = re.search(r"\binstinct\s*([0-9])\b", normalized)
            if instinct_match:
                generation = instinct_match.group(1)
                if re.search(r"\bsolar\b", normalized):
                    variant_signals.add(f"garminwatch:instinct{generation}solar")
                elif re.search(r"\bamoled\b", normalized):
                    variant = f"garminwatch:instinct{generation}amoled"
                    if re.search(r"\bbolt\s+blue\b", normalized):
                        variant = f"{variant}_boltblue"
                    variant_signals.add(variant)
    if brand == "apple" and category in {"tablet pcs", "notebooks"}:
        for match in re.finditer(r"\bm\s*([1-9])\b", raw_normalized):
            code = f"m{match.group(1)}"
            codes.add(code)
            content.add(code)
            numbers.add(match.group(1))
    if category == "grafikkarten":
        for left, middle, right in zip(tokens, tokens[1:], tokens[2:]):
            if (
                left in {"geforce", "rtx"}
                and re.fullmatch(r"\d{3,5}", middle)
                and right == "ti"
            ):
                code = f"rtx{middle}ti"
                codes.add(code)
                content.add(code)
        for match in re.finditer(
            r"\brtx\s*([0-9]{4})\s*(ti)?\b|\brtx([0-9]{4})(ti)?\b",
            raw_normalized,
        ):
            model = match.group(1) or match.group(3)
            has_ti = bool(match.group(2) or match.group(4))
            if model in {"5060", "5070", "5080", "5090"}:
                cluster_variant_signals.add(
                    f"gpurtxmodel:rtx{model}{'ti' if has_ti else ''}"
                )
        for match in re.finditer(
            r"\brx\s*([0-9]{4})\s*(xt)?\b|\brx([0-9]{4})(xt)?\b",
            raw_normalized,
        ):
            model = match.group(1) or match.group(3)
            has_xt = bool(match.group(2) or match.group(4))
            if model in {"9070"}:
                cluster_variant_signals.add(
                    f"gpurxmodel:rx{model}{'xt' if has_xt else ''}"
                )
        if (
            brand == "gigabyte"
            and re.search(r"\brx\s*9070\b|\brx9070\b", normalized)
            and re.search(r"\bgaming\b", normalized)
            and not re.search(r"\bxt\b", normalized)
        ):
            cluster_content.add("gpumodel:gigabyte_rx9070_gaming")
            cluster_codes.add("gigabyterx9070gaming")
            if re.search(r"\b16\s*g\b|\b16gb\b|\b16\s*gb\b", raw_normalized):
                cluster_content.add("gpumodel:gigabyte_rx9070_gaming_16g")
                cluster_codes.add("gigabyterx9070gaming16g")
        if brand == "pine technology":
            has_rx9070xt = bool(
                re.search(r"\brx\s*9070\s*xt\b|\brx9070xt\b", normalized)
            )
            if has_rx9070xt and re.search(r"\bswift\b", normalized):
                cluster_content.add("gpumodel:xfx_rx9070xt_swift")
                cluster_codes.add("xfxrx9070xtswift")
                if re.search(r"\bwhite\b|weiss|weiß", raw_normalized):
                    cluster_content.add("gpumodel:xfx_rx9070xt_swift_white")
                    cluster_codes.add("xfxrx9070xtswiftwhite")
            if has_rx9070xt and re.search(
                r"\bquick\s*silver\b|\bquicksilver\b",
                normalized,
            ):
                cluster_content.add("gpumodel:xfx_rx9070xt_quicksilver")
                cluster_codes.add("xfxrx9070xtquicksilver")
        if brand == "pny" and re.search(r"\brtx\s*5060\s*ti\b|\brtx5060ti\b", normalized):
            if re.search(r"\bargb\b|\btriple\s+fan\b", normalized):
                cluster_variant_signals.add("gpupny5060ti:argb_triple")
            elif re.search(r"\bdual\s+oc\b|\boc\s+dual\b", normalized):
                cluster_variant_signals.add("gpupny5060ti:dual_oc")
            elif re.search(r"\bdual\s+fan\b", normalized):
                cluster_variant_signals.add("gpupny5060ti:dual_fan")
        if brand == "zotac" and re.search(r"\brtx\s*5060\s*ti\b|\brtx5060ti\b", normalized):
            if re.search(r"\btwin\s*edge\b|\btwinedge\b", normalized):
                if re.search(r"\boc\b", normalized):
                    cluster_variant_signals.add("gpuzotac5060ti:twin_edge_oc")
                else:
                    cluster_variant_signals.add("gpuzotac5060ti:twin_edge")
        if (
            brand == "inno3d"
            and re.search(r"\brtx\s*5070\s*ti\b|\brtx5070ti\b", normalized)
            and re.search(r"\bx3\b", normalized)
            and re.search(r"\boc\b", normalized)
        ):
            cluster_content.add("gpumodel:inno3d_rtx5070ti_x3_oc")
            cluster_codes.add("inno3drtx5070tix3oc")
    if category == "fernseher":
        code_aliases: set[str] = set()
        for code in codes:
            match = re.search(r"q(\d{1,2})f2", code)
            if match:
                code_aliases.add(f"q{match.group(1)}f2")
            match = re.fullmatch(r"q(\d{1,2})fa", code)
            if match:
                code_aliases.add(f"q{match.group(1)}f2")
        codes.update(code_aliases)
        content.update(code_aliases)
        if brand == "samsung":
            for match in re.finditer(r"\b(?:gq)?[0-9]{2}q([0-9]{1,2})f([0-9])", normalized):
                variant_signals.add(f"tvmodel:q{match.group(1)}f{match.group(2)}")
    if category == "monitore" and brand == "samsung":
        for match in re.finditer(r"\b(?:l)?s?([0-9]{2}cg55[24])", normalized):
            variant_signals.add(f"monitorsku:{match.group(1)}")
        if re.search(r"\bg55c\b|\bodyssey\s+g5\b", normalized):
            if re.search(r"\b31[,.]5\b|\b80\s*cm\b|\b32\s*(?:zoll|inch)", raw_normalized):
                variant_signals.add("monitorsize:32")
            elif re.search(
                r"\b26[,.]9\b|\b27\s*(?:zoll|inch)?\b|\b68[,.]6\s*cm\b",
                raw_normalized,
            ):
                variant_signals.add("monitorsize:27")
    if category == "handys ohne vertrag" and (
        re.search(r"\bpro\s*\+", raw_normalized)
        or re.search(r"\bpro\s+plus\b", raw_normalized)
    ):
        codes.add("proplus")
        content.add("proplus")
        editions.add("plus")
    if category == "handys ohne vertrag" and brand == "samsung":
        if re.search(r"\benterprise\b", raw_normalized):
            cluster_variant_signals.add("samsungphoneedition:enterprise")
        elif re.search(r"\bgalaxy\b|\bs\s*[0-9]{2}\b|\bsm[-\s]*s", normalized):
            cluster_variant_signals.add("samsungphoneedition:consumer")
    if category == "arbeitsspeicher":
        ram_speeds, ram_layouts, ram_forms, ram_latencies = _extract_ram_specs(
            raw_normalized
        )
        ram_tokens = ram_speeds | ram_layouts | ram_forms | ram_latencies
        content.update(ram_tokens)
        codes.update(ram_tokens)
        sizes.update(ram_layouts | ram_forms)
        for pattern in [
            r"\b(cm[a-z0-9]{10,})\b",
            r"\b(kf[0-9a-z-]{8,})\b",
            r"\b(f[0-9]-[0-9a-z-]{8,})\b",
        ]:
            for match in re.finditer(pattern, raw_normalized):
                part_code = re.sub(r"[^a-z0-9]", "", match.group(1))
                variant_signals.add(f"ramsku:{part_code}")
                content.add(part_code)
                codes.add(part_code)
    if category == "navigationssysteme":
        for match in re.finditer(r"\bmt[-\s]*([a-z])\b", raw_normalized):
            variant_signals.add(f"navtraffic:mt{match.group(1)}")
        if brand == "garmin":
            for match in re.finditer(
                r"\bdrive\s*smart(?:tm)?\s*([0-9]{2})(?:\s*eu)?\b|\bdrivesmart(?:tm)?\s*([0-9]{2})(?:eu)?\b",
                normalized,
            ):
                model = match.group(1) or match.group(2)
                cluster_variant_signals.add(f"navmodel:drivesmart{model}")
                cluster_content.add(f"navmodel:drivesmart{model}")
                cluster_codes.add(f"drivesmart{model}")
            if re.search(r"\balexa\b|amazon\s+alexa", raw_normalized):
                cluster_variant_signals.add("navvoice:alexa")
            elif "drivesmart" in "".join(tokens):
                cluster_variant_signals.add("navvoice:noalexa")
            if (
                "drivesmart" in "".join(tokens)
                and not any(
                    signal.startswith("navtraffic:")
                    for signal in variant_signals | cluster_variant_signals
                )
            ):
                cluster_variant_signals.add("navtraffic:none")
    if brand == "garmin" and category in {"navigationssysteme", "smartwatches"}:
        for match in re.finditer(r"\b010[-\s]*([0-9]{5})[-\s]*([0-9]{2})\b", raw_normalized):
            sku = f"010{match.group(1)}{match.group(2)}"
            variant_signals.add(f"garminsku:{sku}")
            content.add(sku)
            codes.add(sku)
    if brand == "philips" and category == "elektrische zahnbürsten":
        for match in re.finditer(r"\bhx\s*([0-9]{4})\s*/\s*([0-9]{2})\b", raw_normalized):
            variant_signals.add(f"toothbrushsku:hx{match.group(1)}{match.group(2)}")
        for match in re.finditer(r"\b(?:series|serie)\s*([0-9]{4})\b", normalized):
            variant_signals.add(f"toothbrushseries:{match.group(1)}")
    if brand == "de'longhi" and category == "kaffeevollautomaten":
        for match in re.finditer(
            r"\becam\s*([0-9]{3})[.\s]*([0-9]{2})[.\s]*([a-z]{1,3})\b",
            raw_normalized,
        ):
            variant_signals.add(
                f"coffeemodel:ecam{match.group(1)}{match.group(2)}{match.group(3)}"
            )
    if brand == "bosch" and category == "mähroboter":
        for match in re.finditer(r"\b(06008e[0-9]{4})\b", normalized):
            part_code = match.group(1)
            variant_signals.add(f"mowersku:{part_code}")
            content.add(part_code)
            codes.add(part_code)
        if re.search(r"\bsolo\b|\bohne\s+akku\b", raw_normalized):
            variant_signals.add("mowerbundle:solo")
        elif re.search(r"replacement\s+blades|ersatzmesser", raw_normalized):
            variant_signals.add("mowerbundle:akku_blades")
        elif re.search(
            r"\b(?:1x\s*)?akku\b|ladegeraet|ladegerät",
            raw_normalized,
        ):
            variant_signals.add("mowerbundle:akku")
    if brand == "dji" and category == "drohnen":
        for match in re.finditer(r"\bmini\s+([0-9])\s+pro\b", raw_normalized):
            variant_signals.add(f"dronemodel:mini{match.group(1)}pro")
        for match in re.finditer(r"\brc[-\s]*(n?[0-9])\b", raw_normalized):
            variant_signals.add(f"droneremote:rc{match.group(1).replace('-', '')}")
    if brand == "dji" and category == "mikrofone":
        mic_match = re.search(
            r"\bmic\s*([0-9])\b|\bdji\s*mic\s*([0-9])\b|\bdjimic\s*([0-9])\b",
            normalized,
        )
        if mic_match:
            generation = mic_match.group(1) or mic_match.group(2) or mic_match.group(3)
            token = f"djimic:{generation}"
            cluster_content.add(token)
            cluster_codes.add(token)
        mic_mini_match = re.search(r"\bmic\s+mini(?:\s*([0-9]))?\b", normalized)
        if mic_mini_match:
            generation = mic_mini_match.group(1) or "1"
            token = f"djimicmini:{generation}"
            cluster_content.add(token)
            cluster_codes.add(token)
        bundle_match = re.search(
            r"\b([12])\s*(?:tx|sender)\s*\+\s*([12])\s*(?:rx|empfaenger|empfänger)\b",
            raw_normalized,
        )
        if bundle_match:
            cluster_variant_signals.add(
                f"micbundle:{bundle_match.group(1)}tx{bundle_match.group(2)}rx"
            )
        elif re.search(r"\b1\s+sender\s+\+\s+1\s+empfaenger\b", raw_normalized):
            cluster_variant_signals.add("micbundle:1tx1rx")
        if re.search(
            r"\bcharging\s+case\b|\bladecase\b|\bladeschale\b|\bcharger\b",
            raw_normalized,
        ):
            cluster_variant_signals.add("micbundle:charging_case")
        if re.search(r"\bmobile\s+rx\b|\bhandy[-\s]*empfaenger\b|\bsmartphone\b", raw_normalized):
            cluster_variant_signals.add("miccomponent:mobile_rx")
        elif re.search(r"\brx\b|\bempfaenger\b|\bempfänger\b|\breceiver\b", raw_normalized):
            cluster_variant_signals.add("miccomponent:rx")
        if re.search(r"\btx\b|\bsender\b|\btransmitter\b", raw_normalized):
            cluster_variant_signals.add("miccomponent:tx")
    if category == "e-bikes":
        for size_match in re.finditer(
            r"(?:^|[\s/,-])(?:gr\.?\s*)?(xs|s|m|l|xl)(?:[\s/,-]|$)",
            raw_normalized,
        ):
            size_token = f"bikeframe_size:{size_match.group(1)}"
            sizes.add(size_token)
            cluster_content.add(size_token)
        if brand == "haibike":
            for model_match in re.finditer(r"\btrekking\s+([0-9])\b", normalized):
                model = f"ebikemodel:haibike_trekking_{model_match.group(1)}"
                cluster_content.add(model)
                cluster_codes.add(model.replace(":", ""))
        elif brand == "cube":
            for model_match in re.finditer(
                r"\bkathmandu\s+hybrid\s+(one|exc|pro|slx)?\s*([0-9]{3})\b",
                normalized,
            ):
                tier = model_match.group(1) or "base"
                model = f"ebikemodel:cube_kathmandu_{tier}_{model_match.group(2)}"
                cluster_content.add(model)
                cluster_codes.add(model.replace(":", ""))
        elif brand == "fischer":
            for model_match in re.finditer(r"\bcita\s*([0-9]{4})\b", normalized):
                model = f"ebikemodel:fischer_cita_{model_match.group(1)}"
                cluster_content.add(model)
                cluster_codes.add(model.replace(":", ""))
        elif brand == "zündapp":
            for model_match in re.finditer(r"\bx\s*([0-9]{3})\b", normalized):
                model = f"ebikemodel:zuendapp_x{model_match.group(1)}"
                cluster_content.add(model)
                cluster_codes.add(model.replace(":", ""))
        elif brand == "adore":
            for model_match in re.finditer(r"\bgtr[-\s]*([0-9]{3})\b", normalized):
                model = f"ebikemodel:adore_gtr_{model_match.group(1)}"
                cluster_content.add(model)
                cluster_codes.add(model.replace(":", ""))
        if re.search(r"\bdiamant\b|\bherren\b", normalized):
            cluster_variant_signals.add("bikeframe:diamant")
        if re.search(r"\btrapez(?:e)?\b|\bdamen\b", normalized):
            cluster_variant_signals.add("bikeframe:trapez")
        if re.search(
            r"\bwave\b|\bwa\b|\beasy\s*entry\b|\blow[-\s]*step\b|\btiefeinsteiger\b",
            normalized,
        ):
            cluster_variant_signals.add("bikeframe:wave")
    if category in {"systemkameras", "kompaktkameras"}:
        if brand == "nikon" and re.search(r"\bz\s*f\b|\bzf\b", normalized):
            cluster_content.add("camera:nikon_zf")
            cluster_codes.add("nikonzf")
        if brand == "sony" and re.search(r"\brx\s*100\b|\brx100\b", normalized):
            cluster_content.add("camera:sony_rx100")
            cluster_codes.add("sonyrx100")
            if re.search(r"\brx\s*100\s*m\s*7\s*a\b|\brx100m7a\b", normalized):
                cluster_variant_signals.add("cameramodel:rx100m7a")
            elif re.search(
                r"\brx\s*100\s*(?:vii|7)\b|\brx100vii\b|\bmark\s*vii\b",
                normalized,
            ):
                cluster_variant_signals.add("cameramodel:rx100vii")
    if category in {"notebooks", "tablet pcs"}:
        for match in re.finditer(
            r"\b(?:core\s+)?ultra\s+[579]\s+([0-9]{3}[a-z]{1,2})\b",
            raw_normalized,
        ):
            variant_signals.add(f"cpu:{match.group(1)}")
        for match in re.finditer(
            r"\bx1p[-\s]*([0-9]{2})[-\s]*[0-9]{3}\b",
            raw_normalized,
        ):
            variant_signals.add(f"cpu:x1p{match.group(1)}")
    if category == "notebooks":
        if re.search(r"\bwqxga\b|\b2880\s*x\s*1800\b", raw_normalized):
            cluster_variant_signals.add("nbdisplay:wqxga")
        elif re.search(r"\bwuxga\b|\b1920\s*x\s*1200\b", raw_normalized):
            cluster_variant_signals.add("nbdisplay:wuxga")
    if category == "tablet pcs":
        if brand == "samsung":
            if re.search(r"\benterprise\b", raw_normalized):
                cluster_variant_signals.add("samsungtabedition:enterprise")
            elif re.search(r"\bgalaxy\s+tab\b|\btab\s+[as]\b", normalized):
                cluster_variant_signals.add("samsungtabedition:consumer")
            model_match = re.search(
                r"\btab\s+s\s*([0-9]{1,2})\s*(fe)?",
                raw_normalized,
            )
            if model_match:
                generation = model_match.group(1)
                has_fe = bool(model_match.group(2))
                has_plus = bool(
                    re.search(
                        rf"\btab\s+s\s*{re.escape(generation)}\s*(?:fe\s*)?(?:\+|plus)",
                        raw_normalized,
                    )
                )
                if has_fe and has_plus and re.search(
                    r"\bx\s*520\b|\b10_?9(?:0)?zoll\b|\b10\s*9\b|\b10\s*90\b",
                    normalized,
                ):
                    has_plus = False
                if has_fe and has_plus:
                    variant_signals.add(f"samsungtabtier:s{generation}feplus")
                elif has_fe:
                    variant_signals.add(f"samsungtabtier:s{generation}fe")
                elif has_plus:
                    variant_signals.add(f"samsungtabtier:s{generation}plus")
                else:
                    variant_signals.add(f"samsungtabtier:s{generation}")
            for model_code in re.finditer(
                r"\b(?:sm[-\s]*)?x\s*([0-9]{3})([a-z]{0,4})\b",
                normalized,
            ):
                variant_signals.add(f"samsungtabsku:x{model_code.group(1)}")
            if re.search(
                r"\bwi[-\s]*fi\s*\+\s*(?:5g|cellular)\b|\bcellular\b|\b5g\b",
                raw_normalized,
            ):
                variant_signals.add("samsungtabcell:cellular")
            elif re.search(r"\bwi[-\s]*fi\b|\bwlan\b", raw_normalized):
                variant_signals.add("samsungtabcell:wifi")
        elif brand == "xiaomi":
            model_match = re.search(
                r"\bredmi\s+pad\s*([0-9])(?:\s*(pro))?\b",
                normalized,
            )
            if model_match:
                model = f"redmipad{model_match.group(1)}{model_match.group(2) or ''}"
                cluster_content.add(f"tabmodel:{model}")
                cluster_codes.add(model)
                cluster_variant_signals.add(f"xiaomitabmodel:{model}")
            xiaomi_pad_match = re.search(
                r"\bxiaomi\s+pad\s*([0-9])(?:\s*(pro|ultra))?\b",
                normalized,
            )
            if xiaomi_pad_match:
                model = (
                    f"xiaomipad{xiaomi_pad_match.group(1)}"
                    f"{xiaomi_pad_match.group(2) or ''}"
                )
                cluster_content.add(f"tabmodel:{model}")
                cluster_codes.add(model)
                cluster_variant_signals.add(f"xiaomitabmodel:{model}")
        elif brand == "lenovo":
            if re.search(
                r"\byoga\s+tab\s+plus\b|\btb\s*520\b|\bzaeg[0-9a-z]{4,}\b",
                normalized,
            ):
                cluster_content.add("tabmodel:lenovo_yoga_tab_plus")
                cluster_codes.add("lenovoyogatabplus")
            if re.search(
                r"\bidea\s+tab\s+plus\b|\btb\s*361\s*fu\b|\bzagf0069se\b",
                normalized,
            ):
                cluster_content.add("tabmodel:lenovo_idea_tab_plus")
                cluster_codes.add("lenovoideatabplus")
            if re.search(
                r"\bidea\s+tab\s+pro\b|\bzae50132se\b",
                normalized,
            ):
                cluster_content.add("tabmodel:lenovo_idea_tab_pro")
                cluster_codes.add("lenovoideatabpro")
            for sku_match in re.finditer(r"\b(zae[0-9a-z]{1,8})\b", normalized):
                cluster_variant_signals.add(f"lenovotabsku:{sku_match.group(1)}")
            if re.search(r"\btb\s*373\s*fu\b", normalized):
                cluster_variant_signals.add("lenovotabsku:tb373fu")
            for ram_match in re.finditer(
                r"\b(8|12)\s*/\s*256\s*gb\b|\b(8|12)\s*gb\s+ram\b",
                raw_normalized,
            ):
                ram = ram_match.group(1) or ram_match.group(2)
                cluster_variant_signals.add(f"lenovotabram:{ram}gb")
        elif brand == "apple":
            for chip_match in re.finditer(r"\bm\s*([1-9])\b", raw_normalized):
                variant_signals.add(f"applechip:m{chip_match.group(1)}")
            for year_match in re.finditer(r"\b(2024|2025|2026)\b", raw_normalized):
                variant_signals.add(f"year:{year_match.group(1)}")
            if re.search(r"\bipad\s+air\b", normalized) and re.search(
                r"\b2026\b|\bm\s*4\b",
                raw_normalized,
            ):
                cluster_content.add("tabmodel:ipadair_m4_2026")
                cluster_codes.add("ipadairm42026")
            if re.search(
                r"\bwi[-\s]*fi\s*\+\s*(?:5g|cellular)\b|\bcellular\b|\b5g\b",
                raw_normalized,
            ):
                variant_signals.add("ipadcell:cellular")
            elif re.search(r"\bwi[-\s]*fi\b|\bwlan\b", raw_normalized):
                variant_signals.add("ipadcell:wifi")
    if category == "notebooks":
        if brand == "lenovo":
            for part_match in re.finditer(
                r"\b(2[12][a-z0-9]{2}[0-9]{3}[a-z]{2,4})\b",
                normalized,
            ):
                part_code = part_match.group(1)
                variant_signals.add(f"nbsku:{part_code}")
                content.add(part_code)
                codes.add(part_code)
            for family_match in re.finditer(
                r"\bthinkpad\s+([a-zpeltx][0-9]{2,3}s?)\s+(?:gen\s*)?([0-9])\b|\bthinkpad\s+([a-zpeltx][0-9]{2,3}s?)\s+g\s*([0-9])\b",
                normalized,
            ):
                model = family_match.group(1) or family_match.group(3)
                generation = family_match.group(2) or family_match.group(4)
                model_token = f"nbmodel:lenovo_{model}_g{generation}"
                content.add(model_token)
                codes.add(model_token.replace(":", ""))
            for type_match in re.finditer(r"\b(21[a-z0-9]{2}|22[a-z0-9]{2})\b", normalized):
                variant_signals.add(f"nbtype:{type_match.group(1)}")
        elif brand == "microsoft":
            for part_match in re.finditer(r"\b(ep[0-9][-\s]*[0-9]{5})\b", normalized):
                part_code = part_match.group(1).replace(" ", "").replace("-", "")
                variant_signals.add(f"nbsku:{part_code}")
                content.add(part_code)
                codes.add(part_code)
            if re.search(r"\bsurface\s+laptop\s*(?:7)?\b", normalized):
                content.add("nbmodel:surface_laptop")
                codes.add("surfacelaptop")
            for size_match in re.finditer(
                r"\b(13|13_8|15)\s*(?:zoll|inch)?\b|\b(13|15)[,.](8|0)?\s*(?:zoll|inch|\")\b",
                normalized,
            ):
                size_value = size_match.group(1)
                if not size_value and size_match.group(2):
                    size_value = size_match.group(2)
                    if size_match.group(3):
                        size_value = f"{size_value}_{size_match.group(3)}"
                if size_value in {"13", "13_8", "15"}:
                    size_token = f"nbsize:{size_value}"
                    variant_signals.add(size_token)
                    content.add(size_token)
                    sizes.add(size_token)
        elif brand == "apple":
            family_match = re.search(r"\bmacbook\s+(air|pro)\b", normalized)
            if family_match:
                family = family_match.group(1)
                content.add(f"nbmodel:macbook_{family}")
                codes.add(f"macbook{family}")
                size_match = re.search(
                    rf"\bmacbook\s+{family}\s+(13|14|15|16)\b|\b(13|14|15|16)(?:[,.]([0-9]))?\s*(?:zoll|inch)\b|\b(13|14|15|16)_\d+zoll\b",
                    normalized,
                )
                if size_match:
                    size_value = (
                        size_match.group(1)
                        or size_match.group(2)
                        or size_match.group(4)
                    )
                    content.add(f"nbmodel:macbook_{family}_{size_value}")
                    codes.add(f"macbook{family}{size_value}")
                    variant_signals.add(f"nbsize:{size_value}")
            for chip_match in re.finditer(r"\bm\s*([1-9])\s*(pro|max|ultra)?\b", raw_normalized):
                variant_signals.add(
                    f"applechip:m{chip_match.group(1)}{chip_match.group(2) or ''}"
                )
            for year_match in re.finditer(r"\b(2024|2025|2026)\b", raw_normalized):
                variant_signals.add(f"year:{year_match.group(1)}")
            for part_match in re.finditer(r"\b([a-z]{3,4}[0-9]{1,2}d/a)\b", raw_normalized):
                part_code = part_match.group(1).replace("/", "")
                variant_signals.add(f"nbsku:{part_code}")
                content.add(part_code)
                codes.add(part_code)
    if variant_signals:
        content.update(variant_signals)
        codes.update(variant_signals)
    for match in re.finditer(r"\b([a-z]{0,5}\d{1,3})\s*\+", raw_normalized):
        code = f"{match.group(1)}plus"
        codes.add(code)
        content.add(code)
    offer = Offer(
        offer_id=row["offer_id"],
        title=row["title"],
        shop=row.get("shop_name", "").casefold(),
        brand=row["brand"].casefold(),
        category=category,
        price=_parse_price(row.get("price_eur", "")),
        normalized=normalized,
        compact="".join(tokens),
        content=frozenset(content),
        codes=frozenset(codes),
        units=frozenset(units),
        storages=frozenset(storages),
        connectivity=frozenset(connectivity),
        editions=frozenset(editions),
        colors=frozenset(colors),
        sizes=frozenset(sizes),
        numbers=frozenset(numbers),
        ram_speeds=frozenset(ram_speeds),
        ram_layouts=frozenset(ram_layouts),
        ram_forms=frozenset(ram_forms),
        ram_latencies=frozenset(ram_latencies),
        variant_signals=frozenset(variant_signals),
        cluster_content=frozenset(cluster_content),
        cluster_codes=frozenset(cluster_codes),
        cluster_variant_signals=frozenset(cluster_variant_signals),
    )
    alias_content, alias_codes = _extract_tablet_phone_audio_aliases(offer)
    if alias_content or alias_codes:
        return Offer(
            **{
                **offer.__dict__,
                "content": frozenset(set(offer.content) | alias_content),
                "codes": frozenset(set(offer.codes) | alias_codes),
            }
        )
    return offer


def _with_content_weight(offer: Offer, idf: dict[str, float]) -> Offer:
    weight = sum(idf.get(token, 1.0) for token in offer.content) or 1.0
    cluster_weight = (
        sum(idf.get(token, 1.0) for token in _content_tokens(offer, cluster=True))
        or 1.0
    )
    return Offer(
        **{
            **offer.__dict__,
            "content_weight": weight,
            "cluster_content_weight": cluster_weight,
        }
    )


def _build_offers(
    train_rows: list[dict[str, str]],
    predict_rows: list[dict[str, str]],
) -> tuple[dict[str, Offer], dict[str, float]]:
    brands = {row["brand"].casefold() for row in [*train_rows, *predict_rows]}
    stopwords = set(BASE_STOPWORDS) | brands
    raw_offers = [
        _extract_offer(row, stopwords) for row in [*train_rows, *predict_rows]
    ]
    document_frequency: Counter[str] = Counter()
    for offer in raw_offers:
        document_frequency.update(
            offer.content
            | offer.codes
            | offer.cluster_content
            | offer.cluster_codes
            | offer.units
        )
    total = len(raw_offers)
    idf = {
        token: math.log((total + 1) / (count + 1)) + 1.0
        for token, count in document_frequency.items()
    }
    offers = {
        offer.offer_id: _with_content_weight(offer, idf)
        for offer in raw_offers
        if offer.offer_id
    }
    return offers, idf


def _longest_common_substring_length(left: str, right: str) -> int:
    if not left or not right:
        return 0
    return SequenceMatcher(None, left, right, autojunk=False).find_longest_match(
        0, len(left), 0, len(right)
    ).size


def _content_tokens(offer: Offer, *, cluster: bool = False) -> frozenset[str]:
    if not cluster or not offer.cluster_content:
        return offer.content
    return offer.content | offer.cluster_content


def _code_tokens(offer: Offer, *, cluster: bool = False) -> frozenset[str]:
    if not cluster or not offer.cluster_codes:
        return offer.codes
    return offer.codes | offer.cluster_codes


def _variant_tokens(offer: Offer, *, cluster: bool = False) -> frozenset[str]:
    if not cluster or not offer.cluster_variant_signals:
        return offer.variant_signals
    return offer.variant_signals | offer.cluster_variant_signals


def _code_agreement(
    left: Offer,
    right: Offer,
    *,
    fuzzy: bool = True,
    cluster: bool = False,
) -> int:
    best = 0
    for left_code in _code_tokens(left, cluster=cluster):
        for right_code in _code_tokens(right, cluster=cluster):
            if left_code == right_code:
                match = len(left_code)
            elif (
                len(left_code) >= 4
                and len(right_code) >= 4
                and (left_code in right_code or right_code in left_code)
            ):
                match = min(len(left_code), len(right_code))
            elif not fuzzy:
                match = 0
            else:
                common = _longest_common_substring_length(left_code, right_code)
                match = (
                    common
                    if common >= 4
                    and common / min(len(left_code), len(right_code)) >= 0.75
                    else 0
                )
            best = max(best, match)
    return best


def _sum_idf(tokens: Iterable[str], idf: dict[str, float]) -> float:
    return sum(idf.get(token, 1.0) for token in tokens)


def _has_conflict(left: frozenset[str], right: frozenset[str]) -> bool:
    return bool(left and right and not (left & right))


def _has_ram_conflict(left: Offer, right: Offer) -> bool:
    if left.category != "arbeitsspeicher" or right.category != "arbeitsspeicher":
        return False
    return any(
        _has_conflict(left_values, right_values)
        for left_values, right_values in [
            (left.ram_speeds, right.ram_speeds),
            (left.ram_layouts, right.ram_layouts),
            (left.ram_forms, right.ram_forms),
            (left.ram_latencies, right.ram_latencies),
        ]
    )


def _watch_case_sizes(offer: Offer) -> frozenset[str]:
    if offer.category != "smartwatches":
        return frozenset()
    return frozenset(size for size in offer.sizes if size.startswith("watchcase_"))


def _has_watch_case_conflict(left: Offer, right: Offer) -> bool:
    return _has_conflict(_watch_case_sizes(left), _watch_case_sizes(right))


def _has_variant_conflict(
    left: Offer,
    right: Offer,
    *,
    cluster: bool = False,
) -> bool:
    left_signals = _variant_tokens(left, cluster=cluster)
    right_signals = _variant_tokens(right, cluster=cluster)
    if not left_signals or not right_signals:
        return False
    dimensions = {
        signal.split(":", 1)[0]
        for signal in left_signals | right_signals
    }
    for dimension in dimensions:
        left_values = {
            signal
            for signal in left_signals
            if signal.startswith(f"{dimension}:")
        }
        right_values = {
            signal
            for signal in right_signals
            if signal.startswith(f"{dimension}:")
        }
        if _has_conflict(frozenset(left_values), frozenset(right_values)):
            return True
    return False


def _features(
    left: Offer,
    right: Offer,
    idf: dict[str, float],
    *,
    fuzzy: bool = True,
    cluster: bool = False,
) -> list[float]:
    if left.brand != right.brand:
        return [
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            1.0,
            1.0,
            1.0,
            1.0,
            3.0,
            1.0,
        ]
    left_content = _content_tokens(left, cluster=cluster)
    right_content = _content_tokens(right, cluster=cluster)
    left_codes = _code_tokens(left, cluster=cluster)
    right_codes = _code_tokens(right, cluster=cluster)
    intersection_weight = _sum_idf(left_content & right_content, idf)
    union_weight = _sum_idf(left_content | right_content, idf) or 1.0
    if cluster:
        min_weight = (
            min(left.cluster_content_weight, right.cluster_content_weight) or 1.0
        )
    else:
        min_weight = min(left.content_weight, right.content_weight) or 1.0
    code_best = _code_agreement(left, right, fuzzy=fuzzy, cluster=cluster)
    if fuzzy:
        compact_lcs = _longest_common_substring_length(left.compact, right.compact)
        compact_ratio = compact_lcs / max(1, min(len(left.compact), len(right.compact)))
    else:
        compact_ratio = intersection_weight / min_weight
    price_gap = abs(math.log((left.price + 1.0) / (right.price + 1.0)))
    return [
        1.0,
        intersection_weight / union_weight,
        intersection_weight / min_weight,
        compact_ratio,
        code_best / 12.0,
        len(left.units & right.units) / 4.0,
        float(len(left.colors & right.colors)),
        float(len(left.sizes & right.sizes)),
        len(left.numbers & right.numbers) / 4.0,
        float(bool(left_codes and right_codes and code_best < 4)),
        float(_has_conflict(left.colors, right.colors)),
        float(_has_conflict(left.sizes, right.sizes)),
        float(_has_conflict(left.storages, right.storages)),
        float(
            _has_conflict(left.numbers, right.numbers)
            and not (left_codes & right_codes)
        ),
        min(price_gap, 3.0),
        abs(len(left_content) - len(right_content)) / 20.0,
    ]


def pair_score(
    left: Offer,
    right: Offer,
    idf: dict[str, float],
    *,
    fuzzy: bool = True,
) -> float:
    features = _features(left, right, idf, fuzzy=fuzzy, cluster=not fuzzy)
    score = sum(
        weight * ((value - mean) / std)
        for value, weight, mean, std in zip(features, WEIGHTS, MEANS, STDS)
    )
    if not fuzzy:
        score += LEARNED_CLUSTER_BLEND * _learned_cluster_score(
            features,
            left.category,
        )
    return score


def _learned_cluster_score(features: list[float], category: str) -> float:
    model = LEARNED_CATEGORY_MODELS.get(category)
    intercept = model[0] if model else LEARNED_CLUSTER_INTERCEPT
    weights = model[1] if model else LEARNED_CLUSTER_WEIGHTS
    score = intercept + sum(
        weight * value
        for weight, value in zip(weights[:16], features)
    )
    jaccard = features[1]
    containment = features[2]
    compact = features[3]
    code = features[4]
    units = features[5]
    shared_variants = features[6] + features[7] + features[8]
    conflicts = features[9] + features[10] + features[11] + features[12] + features[13]
    price_gap = features[14]
    length_gap = features[15]
    positive_evidence = max(jaccard, containment, compact, code)
    expanded = [
        jaccard * containment,
        containment * compact,
        containment * code,
        compact * code,
        jaccard * code,
        positive_evidence,
        positive_evidence * positive_evidence,
        positive_evidence * price_gap,
        containment * price_gap,
        code * price_gap,
        conflicts,
        conflicts * positive_evidence,
        conflicts * containment,
        shared_variants,
        shared_variants * containment,
        price_gap * price_gap,
        length_gap * length_gap,
        units * containment,
    ]
    return score + sum(
        weight * value
        for weight, value in zip(weights[16:], expanded)
    )


def pair_rank_score(left: Offer, right: Offer, idf: dict[str, float]) -> float:
    base_features = _features(left, right, idf, fuzzy=False, cluster=False)
    features = base_features + [
        float(len(left.connectivity & right.connectivity)),
        float(_has_conflict(left.connectivity, right.connectivity)),
        float(len(left.editions & right.editions)),
        float(_has_conflict(left.editions, right.editions)),
        float(left.shop == right.shop),
        float(left.normalized == right.normalized),
        min(abs(left.price - right.price) / max(left.price, right.price, 1.0), 1.0),
    ]
    return (
        PAIR_RANK_WEIGHTS[0]
        + sum(
        weight * ((value - mean) / std)
        for value, weight, mean, std in zip(
            features, PAIR_RANK_WEIGHTS[1:], PAIR_RANK_MEANS, PAIR_RANK_STDS
        )
        )
        + LEARNED_CLUSTER_BLEND * _learned_cluster_score(
            base_features,
            left.category,
        )
    )


class UnionFind:
    def __init__(self, ids: Iterable[str]) -> None:
        self.parent = {item: item for item in ids}
        self.members = {item: [item] for item in ids}

    def find(self, item: str) -> str:
        parent = self.parent[item]
        if parent != item:
            parent = self.find(parent)
            self.parent[item] = parent
        return parent

    def union(self, left: str, right: str) -> str:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return left_root
        if len(self.members[left_root]) < len(self.members[right_root]):
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        self.members[left_root].extend(self.members.pop(right_root))
        return left_root

    def clusters(self) -> dict[str, list[str]]:
        clusters: dict[str, list[str]] = defaultdict(list)
        for item in self.parent:
            clusters[self.find(item)].append(item)
        return clusters


def _candidate_pairs(offers: list[Offer]) -> set[tuple[str, str]]:
    token_blocks: dict[str, list[str]] = defaultdict(list)
    for offer in offers:
        for token in (
            offer.content
            | offer.codes
            | offer.cluster_content
            | offer.cluster_codes
            | offer.units
            | offer.colors
            | offer.sizes
        ):
            token_blocks[token].append(offer.offer_id)
    candidates: set[tuple[str, str]] = set()
    for ids in token_blocks.values():
        if len(ids) < 2 or len(ids) > MAX_TOKEN_BLOCK:
            continue
        ids = sorted(ids)
        for index, left in enumerate(ids):
            for right in ids[index + 1 :]:
                candidates.add((left, right))
    return candidates


def _can_merge(
    left_cluster: list[str],
    right_cluster: list[str],
    scores: dict[tuple[str, str], float],
    offers: dict[str, Offer],
    idf: dict[str, float],
) -> bool:
    if len(left_cluster) + len(right_cluster) > MAX_CLUSTER_SIZE:
        return False
    left_shops = {offers[offer_id].shop for offer_id in left_cluster}
    right_shops = {offers[offer_id].shop for offer_id in right_cluster}
    if left_shops & right_shops:
        return False
    values: list[float] = []
    for left in left_cluster:
        for right in right_cluster:
            if _has_conflict(offers[left].connectivity, offers[right].connectivity):
                return False
            if (
                offers[left].category in STORAGE_HARD_CONFLICT_CATEGORIES
                and _has_conflict(offers[left].storages, offers[right].storages)
            ):
                return False
            if (
                offers[left].category in COLOR_HARD_CONFLICT_CATEGORIES
                and _has_conflict(offers[left].colors, offers[right].colors)
            ):
                return False
            if (
                offers[left].category in SIZE_HARD_CONFLICT_CATEGORIES
                and _has_conflict(offers[left].sizes, offers[right].sizes)
            ):
                return False
            if _has_watch_case_conflict(offers[left], offers[right]):
                return False
            if _has_ram_conflict(offers[left], offers[right]):
                return False
            if _has_variant_conflict(offers[left], offers[right], cluster=True):
                return False
            key = (left, right) if left < right else (right, left)
            score = scores.get(key)
            if score is None:
                score = pair_score(offers[left], offers[right], idf, fuzzy=False)
                scores[key] = score
            values.append(score)
    if not values:
        return False
    return (
        min(values) >= CLUSTER_MERGE_MIN_THRESHOLD
        and sum(values) / len(values) >= CLUSTER_MERGE_MEAN_THRESHOLD
    )


def _score_between(
    left: str,
    right: str,
    scores: dict[tuple[str, str], float],
    offers: dict[str, Offer],
    idf: dict[str, float],
) -> float:
    key = (left, right) if left < right else (right, left)
    score = scores.get(key)
    if score is None:
        score = pair_score(offers[left], offers[right], idf, fuzzy=False)
        scores[key] = score
    return score


def _split_weak_cluster(
    cluster: list[str],
    scores: dict[tuple[str, str], float],
    offers: dict[str, Offer],
    idf: dict[str, float],
) -> list[list[str]]:
    if len(cluster) < WEAK_CLUSTER_SPLIT_MIN_SIZE:
        return [cluster]

    threshold = WEAK_CLUSTER_SPLIT_THRESHOLD + (
        WEAK_CLUSTER_SPLIT_SIZE_STEP
        * max(0, len(cluster) - WEAK_CLUSTER_SPLIT_MIN_SIZE + 2)
    )
    uf = UnionFind(cluster)
    for index, left in enumerate(cluster):
        for right in cluster[index + 1 :]:
            left_offer = offers[left]
            right_offer = offers[right]
            rank_score = pair_rank_score(left_offer, right_offer, idf)
            graph_score = _score_between(left, right, scores, offers, idf)
            strong_keep = (
                graph_score >= STRONG_SPLIT_KEEP_THRESHOLD
                and not _has_conflict(left_offer.connectivity, right_offer.connectivity)
                and not _has_conflict(left_offer.storages, right_offer.storages)
                and not (
                    left_offer.category in COLOR_HARD_CONFLICT_CATEGORIES
                    and _has_conflict(left_offer.colors, right_offer.colors)
                )
                and not (
                    left_offer.category in SIZE_HARD_CONFLICT_CATEGORIES
                    and _has_conflict(left_offer.sizes, right_offer.sizes)
                )
                and not _has_watch_case_conflict(left_offer, right_offer)
                and not _has_ram_conflict(left_offer, right_offer)
                and not _has_variant_conflict(left_offer, right_offer, cluster=True)
                and not (
                    _has_conflict(left_offer.numbers, right_offer.numbers)
                    and not (left_offer.codes & right_offer.codes)
                )
            )
            if rank_score >= threshold or strong_keep:
                uf.union(left, right)

    components = list(uf.clusters().values())
    return components if len(components) > 1 else [cluster]


def _has_cluster_conflict(
    left_cluster: list[str],
    right_cluster: list[str],
    offers: dict[str, Offer],
) -> bool:
    if len(left_cluster) + len(right_cluster) > MAX_CLUSTER_SIZE:
        return True
    if {offers[offer_id].shop for offer_id in left_cluster} & {
        offers[offer_id].shop for offer_id in right_cluster
    }:
        return True
    for left in left_cluster:
        left_offer = offers[left]
        for right in right_cluster:
            right_offer = offers[right]
            if _has_conflict(left_offer.connectivity, right_offer.connectivity):
                return True
            if _has_conflict(left_offer.storages, right_offer.storages):
                return True
            if _has_conflict(left_offer.sizes, right_offer.sizes):
                return True
            if _has_watch_case_conflict(left_offer, right_offer):
                return True
            if (
                left_offer.category in COLOR_HARD_CONFLICT_CATEGORIES
                and _has_conflict(left_offer.colors, right_offer.colors)
            ):
                return True
            if _has_ram_conflict(left_offer, right_offer):
                return True
            if _has_variant_conflict(left_offer, right_offer, cluster=True):
                return True
            if _has_conflict(left_offer.numbers, right_offer.numbers) and not (
                left_offer.codes & right_offer.codes
            ):
                return True
    return False


def _has_global_remerge_conflict(
    left_cluster: list[str],
    right_cluster: list[str],
    offers: dict[str, Offer],
) -> bool:
    if len(left_cluster) + len(right_cluster) > MAX_CLUSTER_SIZE:
        return True
    if {offers[offer_id].shop for offer_id in left_cluster} & {
        offers[offer_id].shop for offer_id in right_cluster
    }:
        return True
    for left in left_cluster:
        left_offer = offers[left]
        for right in right_cluster:
            right_offer = offers[right]
            if _has_conflict(left_offer.connectivity, right_offer.connectivity):
                return True
            if (
                left_offer.category in STORAGE_HARD_CONFLICT_CATEGORIES
                and _has_conflict(left_offer.storages, right_offer.storages)
            ):
                return True
            if (
                left_offer.category in COLOR_HARD_CONFLICT_CATEGORIES
                and _has_conflict(left_offer.colors, right_offer.colors)
            ):
                return True
            if (
                left_offer.category in SIZE_HARD_CONFLICT_CATEGORIES
                and _has_conflict(left_offer.sizes, right_offer.sizes)
            ):
                return True
            if _has_watch_case_conflict(left_offer, right_offer):
                return True
            if _has_ram_conflict(left_offer, right_offer):
                return True
            if _has_variant_conflict(left_offer, right_offer, cluster=True):
                return True
    return False


def _global_remerge_tokens(cluster: list[str], offers: dict[str, Offer]) -> set[str]:
    tokens: set[str] = set()
    for offer_id in cluster:
        offer = offers[offer_id]
        for code in offer.codes | offer.cluster_codes:
            if len(code) < 5:
                continue
            if code in GLOBAL_REMERGE_GENERIC_CODES:
                continue
            if code.startswith(GLOBAL_REMERGE_GENERIC_PREFIXES):
                continue
            tokens.add(code)
    return tokens


def _component_cross_stats(
    left_cluster: list[str],
    right_cluster: list[str],
    scores: dict[tuple[str, str], float],
    offers: dict[str, Offer],
    idf: dict[str, float],
) -> tuple[float, float, float]:
    rank_scores: list[float] = []
    graph_scores: list[float] = []
    for left in left_cluster:
        for right in right_cluster:
            rank_scores.append(pair_rank_score(offers[left], offers[right], idf))
            graph_scores.append(_score_between(left, right, scores, offers, idf))
    return (
        min(rank_scores),
        sum(rank_scores) / len(rank_scores),
        sum(graph_scores) / len(graph_scores),
    )


def _remerge_global_code_clusters(
    clusters: list[list[str]],
    scores: dict[tuple[str, str], float],
    offers: dict[str, Offer],
    idf: dict[str, float],
) -> list[list[str]]:
    if len(clusters) < 2:
        return clusters

    token_blocks: dict[str, list[int]] = defaultdict(list)
    for index, cluster in enumerate(clusters):
        for token in _global_remerge_tokens(cluster, offers):
            token_blocks[token].append(index)

    candidate_pairs: set[tuple[int, int]] = set()
    for indexes in token_blocks.values():
        if len(indexes) < 2 or len(indexes) > GLOBAL_REMERGE_MAX_TOKEN_BLOCK:
            continue
        indexes = sorted(set(indexes))
        for left_offset, left_index in enumerate(indexes):
            for right_index in indexes[left_offset + 1 :]:
                candidate_pairs.add((left_index, right_index))

    uf = UnionFind(range(len(clusters)))
    for left_index, right_index in sorted(candidate_pairs):
        left_root = uf.find(left_index)
        right_root = uf.find(right_index)
        if left_root == right_root:
            continue
        left_cluster = [
            offer_id
            for cluster_index in uf.members[left_root]
            for offer_id in clusters[cluster_index]
        ]
        right_cluster = [
            offer_id
            for cluster_index in uf.members[right_root]
            for offer_id in clusters[cluster_index]
        ]
        if _has_global_remerge_conflict(left_cluster, right_cluster, offers):
            continue
        rank_min, rank_mean, graph_mean = _component_cross_stats(
            left_cluster,
            right_cluster,
            scores,
            offers,
            idf,
        )
        if (
            rank_mean >= GLOBAL_REMERGE_RANK_MEAN_THRESHOLD
            and rank_min >= GLOBAL_REMERGE_RANK_MIN_THRESHOLD
            and graph_mean >= GLOBAL_REMERGE_GRAPH_MEAN_THRESHOLD
        ):
            uf.union(left_index, right_index)

    merged_clusters: list[list[str]] = []
    for cluster_indexes in uf.clusters().values():
        merged_cluster: list[str] = []
        for cluster_index in cluster_indexes:
            merged_cluster.extend(clusters[cluster_index])
        merged_clusters.append(merged_cluster)
    return merged_clusters


def _samsung_phone_color_key(offer: Offer) -> str | None:
    if offer.brand != "samsung" or offer.category != "handys ohne vertrag":
        return None
    normalized = offer.normalized
    raw_normalized = unicodedata.normalize("NFKC", offer.title.casefold()).replace(
        "ß",
        "ss",
    )
    patterns = [
        (
            "titanium_jetblack",
            r"titanium[-\s]*jet\s*black|jetblack|jet-black",
        ),
        (
            "titanium_black",
            r"titanium[-\s]*black|titanschwarz|\bblack\b|schwarz",
        ),
        (
            "titanium_gray",
            r"titanium[-\s]*(?:gray|grey)|titanium[-\s]*grau|\bgrau\b|\bgray\b|\bgrey\b",
        ),
        (
            "titanium_whitesilver",
            r"white\s*silver|whitesilver|titanium[-\s]*white\s*silver",
        ),
        (
            "titanium_silver",
            r"titanium[-\s]*silver|titan[-\s]*silber",
        ),
        ("titanium_silverblue", r"silver\s*blue|silverblue"),
        ("silver_shadow", r"silver\s*shadow"),
        ("icy_blue", r"icy\s*blue|icyblue|hellblau|light\s*blue"),
        ("navy", r"\bnavy\b|dunkelblau"),
        ("mint", r"\bmint\b|minze|hellgruen|hellgrün"),
        ("white", r"\bwhite\b|weiss|weiß"),
    ]
    for key, pattern in patterns:
        if re.search(pattern, raw_normalized) or re.search(pattern, normalized):
            return key
    return None


def _samsung_phone_color_split_applies(cluster: list[str], offers: dict[str, Offer]) -> bool:
    if len(cluster) < 4:
        return False
    for offer_id in cluster:
        offer = offers[offer_id]
        if offer.brand != "samsung" or offer.category != "handys ohne vertrag":
            return False
        codes = offer.codes | offer.cluster_codes
        if codes & {
            "galaxys24fe",
            "galaxys25fe",
            "galaxys25ultra",
            "s24plus",
            "s25plus",
        }:
            return True
    return False


def _split_samsung_phone_color_clusters(
    clusters: list[list[str]],
    offers: dict[str, Offer],
) -> list[list[str]]:
    split_clusters: list[list[str]] = []
    for cluster in clusters:
        if not _samsung_phone_color_split_applies(cluster, offers):
            split_clusters.append(cluster)
            continue
        groups: dict[str, list[str]] = defaultdict(list)
        has_unknown = False
        for offer_id in cluster:
            color_key = _samsung_phone_color_key(offers[offer_id])
            if color_key is None:
                has_unknown = True
                break
            groups[color_key].append(offer_id)
        if has_unknown or len(groups) < 2:
            split_clusters.append(cluster)
            continue
        split_clusters.extend(groups.values())
    return split_clusters


def _remerge_split_components(
    components: list[list[str]],
    scores: dict[tuple[str, str], float],
    offers: dict[str, Offer],
    idf: dict[str, float],
) -> list[list[str]]:
    if len(components) < 2:
        return components

    uf = UnionFind(range(len(components)))
    edges: list[tuple[float, int, int]] = []
    for left_index, left_cluster in enumerate(components):
        for right_index, right_cluster in enumerate(
            components[left_index + 1 :],
            start=left_index + 1,
        ):
            if _has_cluster_conflict(left_cluster, right_cluster, offers):
                continue
            rank_min, rank_mean, graph_mean = _component_cross_stats(
                left_cluster,
                right_cluster,
                scores,
                offers,
                idf,
            )
            if (
                rank_mean >= POST_REMERGE_RANK_MEAN_THRESHOLD
                and rank_min >= POST_REMERGE_RANK_MIN_THRESHOLD
                and graph_mean >= POST_REMERGE_GRAPH_MEAN_THRESHOLD
            ):
                edges.append((rank_mean + graph_mean / 10.0, left_index, right_index))

    for _, left_index, right_index in sorted(edges, reverse=True):
        left_root = uf.find(left_index)
        right_root = uf.find(right_index)
        if left_root == right_root:
            continue
        left_cluster = [
            offer_id
            for component_index in uf.members[left_root]
            for offer_id in components[component_index]
        ]
        right_cluster = [
            offer_id
            for component_index in uf.members[right_root]
            for offer_id in components[component_index]
        ]
        if not _has_cluster_conflict(left_cluster, right_cluster, offers):
            uf.union(left_index, right_index)

    merged_components: list[list[str]] = []
    for component_indexes in uf.clusters().values():
        merged_cluster: list[str] = []
        for component_index in component_indexes:
            merged_cluster.extend(components[component_index])
        merged_components.append(merged_cluster)
    return merged_components


def _cluster(
    predict_offers: list[Offer],
    idf: dict[str, float],
) -> tuple[dict[str, str], dict[str, int]]:
    by_block: dict[str, list[Offer]] = defaultdict(list)
    for offer in predict_offers:
        by_block[offer.brand].append(offer)

    predictions: dict[str, str] = {}
    diagnostic_counts = {
        "blocking_blocks": len(by_block),
        "candidate_pairs": 0,
        "scored_edges": 0,
        "accepted_merges": 0,
        "post_split_clusters": 0,
        "post_remerge_clusters": 0,
        "global_remerge_clusters": 0,
        "samsung_phone_color_split_clusters": 0,
        "predicted_clusters": 0,
    }
    for block_index, block in enumerate(by_block.values(), start=1):
        if len(block) == 1:
            predictions[block[0].offer_id] = f"offerweave:{block_index}:0"
            diagnostic_counts["predicted_clusters"] += 1
            continue

        by_id = {offer.offer_id: offer for offer in block}
        pair_scores: dict[tuple[str, str], float] = {}
        edges: list[tuple[float, str, str]] = []
        candidates = _candidate_pairs(block)
        diagnostic_counts["candidate_pairs"] += len(candidates)
        for left_id, right_id in candidates:
            score = pair_score(by_id[left_id], by_id[right_id], idf, fuzzy=False)
            key = (left_id, right_id) if left_id < right_id else (right_id, left_id)
            pair_scores[key] = score
            if score >= CLUSTER_EDGE_THRESHOLD:
                edges.append((score, left_id, right_id))
        diagnostic_counts["scored_edges"] += len(edges)

        uf = UnionFind(by_id)
        edges.sort(reverse=True)
        for _, left_id, right_id in edges:
            left_root = uf.find(left_id)
            right_root = uf.find(right_id)
            if left_root == right_root:
                continue
            left_cluster = uf.members[left_root]
            right_cluster = uf.members[right_root]
            if _can_merge(left_cluster, right_cluster, pair_scores, by_id, idf):
                uf.union(left_id, right_id)
                diagnostic_counts["accepted_merges"] += 1

        final_clusters: list[list[str]] = []
        for ids in uf.members.values():
            split_clusters = _split_weak_cluster(ids, pair_scores, by_id, idf)
            remerged_clusters = _remerge_split_components(
                split_clusters,
                pair_scores,
                by_id,
                idf,
            )
            diagnostic_counts["post_remerge_clusters"] += len(split_clusters) - len(
                remerged_clusters
            )
            final_clusters.extend(remerged_clusters)
        diagnostic_counts["post_split_clusters"] += len(final_clusters) - len(
            uf.members
        )
        global_remerged_clusters = _remerge_global_code_clusters(
            final_clusters,
            pair_scores,
            by_id,
            idf,
        )
        diagnostic_counts["global_remerge_clusters"] += len(final_clusters) - len(
            global_remerged_clusters
        )
        final_clusters = global_remerged_clusters
        color_split_clusters = _split_samsung_phone_color_clusters(
            final_clusters,
            by_id,
        )
        diagnostic_counts["samsung_phone_color_split_clusters"] += len(
            color_split_clusters
        ) - len(final_clusters)
        final_clusters = color_split_clusters

        for cluster_number, ids in enumerate(final_clusters):
            cluster_id = f"offerweave:{block_index}:{cluster_number}"
            for offer_id in ids:
                predictions[offer_id] = cluster_id
        diagnostic_counts["predicted_clusters"] += len(final_clusters)
    return predictions, diagnostic_counts


def run(
    *,
    train_path: str | Path,
    predict_path: str | Path,
    output_path: str | Path,
    pair_input_path: str | Path,
    pair_scores_path: str | Path,
) -> None:
    started = time.monotonic()
    train_rows = _read_csv(train_path)
    predict_rows = _read_csv(predict_path)
    offers, idf = _build_offers(train_rows, predict_rows)
    predict_offers = [offers[row["offer_id"]] for row in predict_rows]

    predictions, cluster_metrics = _cluster(predict_offers, idf)
    with Path(output_path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["offer_id", "cluster_id"])
        writer.writeheader()
        for row in predict_rows:
            writer.writerow(
                {
                    "offer_id": row["offer_id"],
                    "cluster_id": predictions[row["offer_id"]],
                }
            )

    pair_rows = _read_csv(pair_input_path)
    with Path(pair_scores_path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["pair_id", "score"])
        writer.writeheader()
        for row in pair_rows:
            score = pair_rank_score(
                offers[row["offer_id_left"]], offers[row["offer_id_right"]], idf
            )
            writer.writerow({"pair_id": row["pair_id"], "score": f"{score:.12g}"})

    metrics = {
        "package": "offerweave",
        "oracle_category_blocking": False,
        "blocking_key": "brand",
        "category_source": "title_brand_inference",
        "curated_category_features": False,
        "compact_category_inference_signals": True,
        "samsung_watch_sku_aliases": True,
        "huawei_watch_gt_aliases": True,
        "lenovo_yoga_tab_aliases": True,
        "candidate_token_block_max": MAX_TOKEN_BLOCK,
        "cluster_edge_threshold": CLUSTER_EDGE_THRESHOLD,
        "cluster_merge_mean_threshold": CLUSTER_MERGE_MEAN_THRESHOLD,
        "cluster_merge_min_threshold": CLUSTER_MERGE_MIN_THRESHOLD,
        "weak_cluster_split_size_step": WEAK_CLUSTER_SPLIT_SIZE_STEP,
        "strong_split_keep_threshold": STRONG_SPLIT_KEEP_THRESHOLD,
        "post_remerge_graph_mean_threshold": POST_REMERGE_GRAPH_MEAN_THRESHOLD,
        "post_remerge_rank_mean_threshold": POST_REMERGE_RANK_MEAN_THRESHOLD,
        "post_remerge_rank_min_threshold": POST_REMERGE_RANK_MIN_THRESHOLD,
        "global_remerge_graph_mean_threshold": GLOBAL_REMERGE_GRAPH_MEAN_THRESHOLD,
        "global_remerge_rank_mean_threshold": GLOBAL_REMERGE_RANK_MEAN_THRESHOLD,
        "global_remerge_rank_min_threshold": GLOBAL_REMERGE_RANK_MIN_THRESHOLD,
        "global_remerge_token_block_max": GLOBAL_REMERGE_MAX_TOKEN_BLOCK,
        "learned_cluster_blend": LEARNED_CLUSTER_BLEND,
        "learned_cluster_features": len(LEARNED_CLUSTER_WEIGHTS),
        "learned_cluster_category_models": len(LEARNED_CATEGORY_MODELS),
        "cluster_only_signal_families": 15,
        "tablet_cluster_only_signals": True,
        "lenovo_tablet_variant_signals": True,
        "samsung_monitor_variant_signals": True,
        "watch_case_hard_conflicts": True,
        "garmin_navtraffic_none_signals": True,
        "samsung_titanium_silver_color_key": True,
        "gpu_cluster_variant_signals": True,
        "samsung_phone_raw_color_splits": True,
        "color_hard_conflict_categories": len(COLOR_HARD_CONFLICT_CATEGORIES),
        "size_hard_conflict_categories": len(SIZE_HARD_CONFLICT_CATEGORIES),
        "ram_layout_module_aliases": True,
        "ram_colon_layout_aliases": True,
        "pair_rank_features": len(PAIR_RANK_MEANS),
        "duration_s": round(time.monotonic() - started, 6),
        "predict_offers": len(predict_rows),
        "train_offers": len(train_rows),
        **cluster_metrics,
    }
    Path("metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", required=True)
    parser.add_argument("--predict", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pair-input", required=True)
    parser.add_argument("--pair-scores", required=True)
    args = parser.parse_args(argv)
    run(
        train_path=args.train,
        predict_path=args.predict,
        output_path=args.output,
        pair_input_path=args.pair_input,
        pair_scores_path=args.pair_scores,
    )
    return 0
