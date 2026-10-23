from .tspccm import scrape as scrape_tspccm
from .tlcs   import scrape as scrape_tlcs
from .tstld  import scrape as scrape_tstld
from .seccm  import scrape as scrape_seccm
from .tsccm  import scrape as scrape_tsccm
from .tssm   import scrape as scrape_tssm

# key = short code shown on the site; order = display order of source chips
ALL_SCRAPERS = {
    "TSPCCM":   scrape_tspccm,   # 台灣胸腔暨重症加護醫學會
    "肺癌學會":  scrape_tlcs,     # 台灣肺癌學會
    "結核學會":  scrape_tstld,    # 台灣結核暨肺部疾病醫學會
    "急救加護":  scrape_seccm,    # 台灣急救加護醫學會
    "重症醫學會": scrape_tsccm,   # 中華民國重症醫學會
    "睡眠學會":  scrape_tssm,     # 台灣睡眠醫學學會
}
