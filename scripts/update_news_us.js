#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, '../data/news_us.json');
const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));

const additions = {
  "NVDA": [
    {
      "date": "2026-05-10",
      "type": "news",
      "title": "Nvidia H200 Chip Shipments Resume to China; ByteDance, Alibaba, Tencent Clear 400,000+ Units",
      "url": "https://www.tomshardware.com/tech-industry/semiconductors/nvidia-prepares-h200-shipments-to-china-as-chip-war-lines-blur",
      "source": "Tom's Hardware",
      "content": "Nvidia is preparing to ship 82,000 H200 AI GPUs to China under revised US export controls allowing H200 sales on a case-by-case basis at 25% tariff. China approved imports for ByteDance, Alibaba, and Tencent totaling 400,000+ units — a major demand reopening ahead of May 20 earnings."
    }
  ],
  "AMD": [
    {
      "date": "2026-05-10",
      "type": "research",
      "title": "AMD Up 320% Over 12 Months: 33 Analysts Buy Consensus, $383 Median Target; MI450 Demand Exceeding Expectations",
      "url": "https://www.fool.com/investing/2026/05/10/is-it-too-late-to-buy-amd-after-12-month-gain-of/",
      "source": "The Motley Fool",
      "content": "Following AMD Q1 2026 blowout results, 33 analysts maintain Buy consensus with median price target $383.45. CEO Lisa Su confirmed MI450 customer demand is exceeding initial expectations; AMD guided Q2 revenue ~$11.2B (+46% YoY)."
    }
  ],
  "INTC": [
    {
      "date": "2026-05-09",
      "type": "announcement",
      "title": "Intel CEO Lip-Bu Tan Confirmed as Computex 2026 Keynote on June 2 Taipei; Nova Lake, Panther Lake, Clearwater Forest to Preview",
      "url": "https://finance.yahoo.com/sectors/technology/articles/intel-ceo-lip-bu-tan-051400503.html",
      "source": "Yahoo Finance / Intel Newsroom",
      "content": "Intel confirmed CEO Lip-Bu Tan will keynote Computex 2026 on June 2 (1:30 PM Taiwan time), previewing Nova Lake (Core Ultra Series 4, up to 52 cores on 18A), Panther Lake Arc G3 handhelds, and AI data center platforms Crescent Island and Jaguar Shores — all built on Intel 18A."
    }
  ],
  "COHR": [
    {
      "date": "2026-05-06",
      "type": "announcement",
      "title": "Nvidia Takes $2B Equity Stake in Coherent; Strategic Co-Packaged Optics Partnership Through Decade-End",
      "url": "https://nvidianews.nvidia.com/news/nvidia-and-coherent-announce-strategic-partnership-to-develop-optics-technology-to-scale-next-generation-data-center-architecture",
      "source": "NVIDIA Newsroom",
      "content": "Nvidia invested $2B in Coherent as part of a strategic co-packaged optics (CPO) partnership with multiyear supply agreement through end of decade. CPO is a $15B+ TAM central to scaling next-gen AI data center architectures; Raymond James raised target to $371, Stifel to $420."
    }
  ],
  "LITE": [
    {
      "date": "2026-05-05",
      "type": "announcement",
      "title": "Lumentum Q3 FY2026: EPS $2.37 Beats by 9%; Q4 Guided ~$985M Record; Stock +16.9% Then Pulled Back on Sector Rotation",
      "url": "https://seekingalpha.com/article/4898818-lumentum-holdings-inc-2026-q3-results-earnings-call-presentation",
      "source": "Seeking Alpha / Lumentum IR",
      "content": "Lumentum Q3 FY2026: EPS $2.37 beat $2.17 estimate by 9.2%; revenue $808M slightly missed $820M consensus. Q4 revenue guided midpoint ~$985M — new quarterly record — and EPS $2.85-3.05 on AI-driven optical demand. Stock initially surged 16.9% then pulled back ~5% the following session."
    }
  ],
  "FN": [
    {
      "date": "2026-05-07",
      "type": "announcement",
      "title": "Fabrinet Q3 FY2026: Record Revenue $1.214B (+39% YoY); $32M Raytec Investment for CPO; Q4 Guided $1.25-1.29B",
      "url": "https://seekingalpha.com/article/4900907-fabrinet-2026-q3-results-earnings-call-presentation",
      "source": "Seeking Alpha / Fabrinet IR",
      "content": "Fabrinet Q3 FY2026: record revenue $1.214B (+39% YoY), EPS $3.72 vs $3.53 estimate; telecom +55%, non-optical communications +52%. Launched two new hyperscaler datacom transceiver programs; made $32M minority investment in Raytec Semiconductor for co-packaged optics. Q4 guided $1.25-1.29B."
    }
  ],
  "APP": [
    {
      "date": "2026-05-10",
      "type": "research",
      "title": "Morgan Stanley: AppLovin June Axon Self-Service Launch Is Key Catalyst; E-Commerce Advertiser Spend +50% Weekly",
      "url": "https://www.thestreet.com/investing/stocks/morgan-stanley-spills-beans-on-whats-next-for-applovin-stock",
      "source": "TheStreet / Morgan Stanley",
      "content": "Morgan Stanley identified June 2026 Axon self-service platform launch as the next pivotal catalyst for APP. E-commerce advertisers show 50% weekly spend growth on Axon; Axon 2.0 model improvements and durable margin expansion prospects highlighted. Reiterated Overweight rating post-Q1."
    }
  ],
  "HUBB": [
    {
      "date": "2026-04-30",
      "type": "announcement",
      "title": "Hubbell Q1 2026: Sales +11% to $1.52B; Acquires NSI Industries for $3B; Raises Full-Year EPS Guidance to $19.30-19.85",
      "url": "https://www.globenewswire.com/news-release/2026/04/30/3284729/0/en/Hubbell-Reports-First-Quarter-2026-Results.html",
      "source": "GlobeNewswire / Hubbell IR",
      "content": "Hubbell Q1 2026: net sales $1.517B (+11% YoY, +8% organic), adj EPS $3.93 beat $3.87 estimate. Announced $3B acquisition of NSI Industries to strengthen electrical connections for data center and grid markets. Raised FY2026 adj EPS guidance to $19.30-19.85."
    },
    {
      "date": "2026-05-04",
      "type": "research",
      "title": "Stephens Raises Hubbell Target to $600, Barclays to $503 After Q1 Beat; Data Center Electrical Demand Cited",
      "url": "https://www.tipranks.com/news/company-announcements/hubbell-shareholders-approve-directors-pay-and-auditor-slate",
      "source": "TipRanks",
      "content": "Stephens raised HUBB target to $600 (from $550), Barclays to $503 (from $481) following Q1 2026 beat and raised guidance. Seven analysts hold Buy consensus averaging $491. Data center and grid electrification cited as structural multi-year demand drivers for Hubbell's electrical products."
    }
  ],
  "POWL": [
    {
      "date": "2026-05-04",
      "type": "announcement",
      "title": "Powell Industries Q2 FY2026: New Orders +97% to $490M; Backlog Hits Record $1.8B; Revenue $296.6M",
      "url": "https://www.globenewswire.com/news-release/2026/05/04/3287156/0/en/powell-industries-announces-second-quarter-fiscal-2026-results.html",
      "source": "GlobeNewswire / Powell Industries IR",
      "content": "Powell Industries Q2 FY2026: revenue $296.6M (+6% YoY), gross margin 29.6%. EPS $1.25 slightly missed $1.39 estimate. New orders surged 97% to $490M, lifting backlog to record $1.8B. Board declared $0.09/share quarterly dividend payable June 17."
    },
    {
      "date": "2026-05-08",
      "type": "news",
      "title": "Powell Industries Surges 10.3% on Landmark $400M+ AI Data Center Order — Largest Contract in Company History",
      "url": "https://www.sahmcapital.com/news/content/why-powell-industries-powl-is-up-103-after-record-q2-backlog-and-landmark-ai-data-center-deal-2026-05-08",
      "source": "Sahm Capital",
      "content": "POWL jumped 10.3% after disclosing a $400M+ greenfield AI data center order — the largest in company history — awarded after Q2 quarter-end. Confirms Powell as a key medium-voltage switchgear supplier for AI infrastructure buildout alongside $1.8B record backlog."
    }
  ],
  "ANET": [
    {
      "date": "2026-05-05",
      "type": "announcement",
      "title": "Arista Networks Q1 2026: Revenue $2.71B (+35% YoY); AI Fabric Target Raised to $3.5B; Full-Year Outlook $11.5B",
      "url": "https://www.arista.com/en/company/news/press-release/24017-pr-20260505",
      "source": "Arista Networks IR",
      "content": "Arista Q1 2026: revenue $2.709B (+35.1% YoY), EPS $0.87 beat $0.79 estimate. Raised full-year 2026 revenue outlook to ~$11.5B (+27.7%) and AI fabric sales target from $3.25B to $3.5B. Management flagged 1-2 year supply constraints across wafers, silicon, optics, and memory."
    },
    {
      "date": "2026-05-05",
      "type": "news",
      "title": "Arista Claims #1 Market Share in High-Speed Switching (>10GbE); Meta and Microsoft AI Fabric Among Top Customers",
      "url": "https://seekingalpha.com/news/4586520-arista-outlines-27_7-percent-2026-revenue-growth-to-11_5b-while-targeting-3_5b-in-ai-fabric",
      "source": "Seeking Alpha",
      "content": "Arista confirmed #1 market share in >10Gb Ethernet switching on Q1 2026 call. Gross margin pressure expected as company pays premium costs to secure supply. Meta and Microsoft AI fabric deployments driving demand for Arista's AI back-end (scale-out) and front-end (scale-up) networks."
    }
  ],
  "ARM": [
    {
      "date": "2026-05-06",
      "type": "announcement",
      "title": "Arm Holdings Q4 FY2026: Record Revenue $1.49B; Data Center Royalties Double YoY; AGI CPU Demand Exceeds $20B in Six Weeks",
      "url": "https://www.businesswire.com/news/home/20260506216985/en/Arm-Holdings-plc-Reports-Results-for-the-Fourth-Quarter-and-Fiscal-Year-Ended-2026",
      "source": "BusinessWire / Arm Newsroom",
      "content": "Arm Q4 FY2026: record revenue $1.49B (licensing +29% YoY, royalty +11% YoY); full-year revenue $4.92B. EPS $0.60 beat $0.54 estimate. Data center royalty revenue more than doubled YoY. CEO: AGI CPU demand surged past $20B in six weeks, but supply locked for only first $1B — upside back-loaded to FY2027."
    },
    {
      "date": "2026-05-07",
      "type": "news",
      "title": "ARM Stock Falls 7% Despite Record Results on Supply Cap and Negative Smartphone Unit Growth Outlook",
      "url": "https://www.heygotrade.com/en/news/arm-holdings-record-revenue-stock-slides-supply-cap/",
      "source": "HeyGoTrade",
      "content": "ARM shares fell 7.25% to $220.10 on May 7 despite earnings beat. Management withheld guidance raise due to supply constraints limiting near-term upside to FY2027. Smartphone unit growth expected to turn negative from memory chip shortage in handset supply chain."
    }
  ],
  "LRCX": [
    {
      "date": "2026-04-22",
      "type": "announcement",
      "title": "Lam Research Q3 FY2026: Record Revenue $5.84B (+24% YoY); Raises 2026 WFE Industry Forecast to $140B; Q4 Guided $6.6B",
      "url": "https://www.fool.com/earnings/call-transcripts/2026/04/22/lam-research-lrcx-q3-2026-earnings-transcript/",
      "source": "Motley Fool",
      "content": "Lam Research Q3 FY2026: record revenue $5.84B (+24% YoY, +9% QoQ), non-GAAP EPS $1.47 beat $1.38 estimate. Raised 2026 wafer fabrication equipment (WFE) industry spending forecast to $140B (from $135B) with upside bias on AI-driven demand. Q4 guided $6.6B revenue and $1.65 EPS."
    }
  ],
  "CDNS": [
    {
      "date": "2026-04-27",
      "type": "announcement",
      "title": "Cadence Design Q1 2026: Revenue $1.47B (+19% YoY); Raises Full-Year Guidance to $6.18B; TSMC and Lightmatter Partnerships Expanded",
      "url": "https://www.cadence.com/en_US/home/company/newsroom/press-releases/pr-ir/2026/cadence-reports-first-quarter-2026-financial-results.html",
      "source": "Cadence IR",
      "content": "Cadence Q1 2026: revenue $1.47B (+19% YoY), adj EPS $1.96 (+23% YoY). Raised full-year 2026 revenue guidance to $6.18B on AI chip design demand. Expanded TSMC collaboration for advanced process nodes; new partnership with Lightmatter for AI infrastructure photonic interconnects announced."
    }
  ],
  "ORCL": [
    {
      "date": "2026-05-01",
      "type": "policy",
      "title": "Pentagon Clears Oracle Among 8 Tech Firms for Classified AI Networks (IL6/IL7); OCI National-Security Positioning Validated",
      "url": "https://redmondmag.com/articles/2026/05/04/pentagon-expands-ai-deals-with-microsoft.aspx",
      "source": "Redmond Magazine / Breaking Defense",
      "content": "US DoD announced agreements with 8 tech firms — including Oracle, Microsoft, Amazon, Nvidia, Google, SpaceX, OpenAI, and Reflection — to deploy AI on most sensitive classified networks (IL6/IL7). Oracle shares rallied ~6%, reinforcing OCI's national-security cloud positioning alongside AWS GovCloud."
    },
    {
      "date": "2026-05-07",
      "type": "announcement",
      "title": "Oracle Closes $16B AI Campus Funding with Blackstone; 1.4GW Michigan Data Center and $1.65B Datapod Supply Deal",
      "url": "https://247wallst.com/investing/2026/05/06/oracle-stocks-breakout-is-real-and-the-long-term-ai-infrastructure-case-is-only-getting-stronger/",
      "source": "24/7 Wall St.",
      "content": "Oracle finalized $16B in funding (with Blackstone and Related Digital) for a 1GW+ AI campus; separately announced 1.4GW data center partnership with DTE Energy in Michigan and $1.65B six-year supply agreement with Datapod — cementing aggressive OCI AI infrastructure expansion to serve AI training workloads."
    }
  ],
  "PLTR": [
    {
      "date": "2026-05-04",
      "type": "announcement",
      "title": "Palantir Q1 2026: Revenue +85% YoY to $1.63B (Fastest Since IPO); US Revenue +104%; Raises FY2026 Guide to 71% Growth",
      "url": "https://investors.palantir.com/news-details/2026/Palantir-Reports-Q1-2026-U-S--Revenue-Growth-of-104-YY-and-Revenue-Growth-of-85-YY-Raises-FY-2026-Revenue-Guidance-to-71-YY-Growth-and-U-S--Comm-Revenue-Guidance-to-120-YY-Crushing-Consensus-Expectations/",
      "source": "Palantir IR",
      "content": "Palantir Q1 2026: revenue $1.63B (+85% YoY), adj EPS $0.33 beat $0.28 estimate, 60% adj operating margin. US revenue +104% (government +84%, commercial +133%). Raised FY2026 guidance to $7.65-7.66B (+71% YoY) and US commercial to +120% YoY — crushing consensus. AIP platform driving both government and enterprise AI monetization."
    },
    {
      "date": "2026-05-11",
      "type": "news",
      "title": "Palantir Creates Stock Market History: 85% Revenue Growth + 57% FCF Margin — Rare Hyper-Growth Profitability Pairing",
      "url": "https://www.fool.com/investing/2026/05/11/palantir-technologies-has-just-created-history-here/",
      "source": "The Motley Fool",
      "content": "Following record Q1 2026 results, Palantir achieved historic stock market milestones as one of very few large-cap companies combining hyper-growth (85% revenue) with high profitability (57% FCF margin). AIP platform adoption in DoD and enterprise sectors driving both growth vectors simultaneously."
    }
  ],
  "IREN": [
    {
      "date": "2026-05-05",
      "type": "announcement",
      "title": "IREN Acquires Mirantis for ~$625M All-Stock to Strengthen AI Cloud Delivery; 1,500+ Enterprise Kubernetes Customers",
      "url": "https://www.globenewswire.com/news-release/2026/05/05/3287514/0/en/iren-announces-acquisition-of-mirantis-to-strengthen-ai-cloud-delivery-capabilities.html",
      "source": "GlobeNewswire",
      "content": "IREN signed a definitive agreement to acquire Mirantis — a Kubernetes orchestration provider serving 1,500+ enterprise customers — for ~$625M in all-stock. Mirantis is a founding ISV partner of the NVIDIA AI Cloud Ready Initiative, strengthening IREN's managed AI cloud capabilities and enterprise software layer."
    },
    {
      "date": "2026-05-07",
      "type": "announcement",
      "title": "IREN Secures $3.4B Five-Year NVIDIA AI Cloud Contract; NVIDIA Receives Warrants for 30M Shares at $70 (~$2.1B)",
      "url": "https://www.globenewswire.com/news-release/2026/05/07/3290760/0/en/IREN-Secures-3-4bn-AI-Cloud-Contract-with-NVIDIA.html",
      "source": "GlobeNewswire",
      "content": "IREN signed a five-year ~$3.4B managed GPU cloud services contract with NVIDIA, granting NVIDIA the right to purchase up to 30M IREN shares at $70/share (~$2.1B warrants). Underpins IREN's plan to deploy up to 5GW of NVIDIA-designed AI infrastructure; stock surged 13% on May 8."
    },
    {
      "date": "2026-05-07",
      "type": "announcement",
      "title": "IREN Acquires Nostrum Group: Enters Europe with 490MW Secured Power in Spain; Global Portfolio Reaches 5GW",
      "url": "https://www.globenewswire.com/news-release/2026/05/07/3290678/0/en/IREN-Expands-AI-Cloud-Platform-to-Europe-with-Acquisition-of-Nostrum-Group.html",
      "source": "GlobeNewswire",
      "content": "IREN agreed to acquire Ingenostrum S.L. (Nostrum Group), a Spanish data center developer with ~490MW grid-connected power in Spain plus an additional development pipeline — expanding IREN's total secured global power portfolio to 5GW."
    },
    {
      "date": "2026-05-07",
      "type": "announcement",
      "title": "IREN Q3 FY2026 Revenue $144.8M Misses $219.9M Estimate as Bitcoin-to-AI Infrastructure Pivot Continues",
      "url": "https://www.globenewswire.com/news-release/2026/05/07/3290719/0/en/iren-business-update-and-q3-fy26-results.html",
      "source": "GlobeNewswire",
      "content": "IREN Q3 FY2026 revenue $144.8M significantly missed analyst consensus of ~$219.9M as the company continues pivot from Bitcoin mining to AI infrastructure. Revenue miss was overshadowed by the simultaneous NVIDIA $3.4B contract, Mirantis, and Nostrum announcements the same week."
    },
    {
      "date": "2026-05-11",
      "type": "announcement",
      "title": "IREN Launches $2B Convertible Notes Offering to Fund AI Infrastructure Expansion; Shares Fall ~10%",
      "url": "https://www.fool.com/coverage/stock-market-today/2026/05/11/stock-market-today-may-11-iren-falls-after-2-billion-convertible-notes-offering-pressures-shares/",
      "source": "The Motley Fool",
      "content": "IREN announced a $2B convertible notes offering to fund AI infrastructure expansion, sending shares down ~9.9% to $55.15 as investors digested dilution risk following the prior week's 13% surge on the NVIDIA deal announcement."
    }
  ],
  "VST": [
    {
      "date": "2026-05-07",
      "type": "announcement",
      "title": "Vistra Q1 2026: Net Income $1.03B; EPS $2.87 Beats by 30%; 2026 Adjusted EBITDA Guidance $6.8-7.6B Reaffirmed",
      "url": "https://www.prnewswire.com/news-releases/vistra-reports-first-quarter-2026-results-302765015.html",
      "source": "PR Newswire / Vistra IR",
      "content": "Vistra Q1 2026: GAAP net income $1.029B (vs -$268M a year ago), EPS $2.87 beat $2.21 consensus by 30%. Revenue $5.64B (from $3.93B). Reaffirmed 2026 Adjusted EBITDA guidance $6.8-7.6B. Retail and generation expansion supports AI data center direct power supply strategy."
    },
    {
      "date": "2026-05-07",
      "type": "news",
      "title": "Vistra Achieves Investment-Grade at Both S&P and Fitch; Dual Rating Triggers Lien Release, Lowers Capital Cost",
      "url": "https://www.prnewswire.com/news-releases/vistra-achieves-investmentgrade-credit-ratings-from-sp-and-fitch-302716271.html",
      "source": "PR Newswire",
      "content": "Fitch upgraded Vistra to BBB- (investment grade), joining S&P's December 2025 upgrade. Dual investment-grade status triggered lien release provisions, expanding Vistra's access to lower-cost capital markets debt and improving financial flexibility for AI data center long-term power agreements."
    }
  ],
  "MPWR": [
    {
      "date": "2026-05-06",
      "type": "announcement",
      "title": "Monolithic Power Q1 2026: Record Revenue $804M (+26% YoY); Raises Capacity Target to $6B; Q2 Guided ~$900M; AI Server Growth 85% YoY",
      "url": "https://seekingalpha.com/article/4899793-monolithic-power-systems-inc-2026-q1-results-earnings-call-presentation",
      "source": "Seeking Alpha / MPWR IR",
      "content": "MPWR Q1 2026: record revenue $804M (+26% YoY, +7% QoQ), adj EPS $5.10 beat $4.90 estimate. Raised manufacturing capacity target to $6B (from $4B). Q2 guided ~$900M. Enterprise data (AI servers DrMOS/VRM for NVIDIA H100/B200) growth raised to 85% YoY from prior 50% floor."
    },
    {
      "date": "2026-05-07",
      "type": "research",
      "title": "Multiple Analysts Raise MPWR Price Targets After Q1 Beat and 85% AI Server Growth Guidance",
      "url": "https://simplywall.st/stocks/us/semiconductors/nasdaq-mpwr/monolithic-power-systems/news/earnings-update-monolithic-power-systems-inc-nasdaqmpwr-just",
      "source": "Simply Wall St",
      "content": "Multiple analysts raised MPWR price targets following Q1 2026 beat and enterprise data growth upgrade to 85% YoY. Communications segment grew 33% sequentially. Structural position in AI server power delivery (DrMOS/VRM) cited as a durable multi-year growth driver for MPWR."
    }
  ],
  "GLW": [
    {
      "date": "2026-05-06",
      "type": "announcement",
      "title": "NVIDIA and Corning: 10x US Optical Manufacturing Expansion; NVIDIA Warrants for Up to $3.2B Corning Investment",
      "url": "https://nvidianews.nvidia.com/news/nvidia-and-corning-announce-long-term-partnership-to-strengthen-us-manufacturing-for-ai-infrastructure",
      "source": "NVIDIA Newsroom / Corning IR",
      "content": "NVIDIA and Corning announced a multiyear partnership: Corning to expand US optical connectivity manufacturing 10x and US fiber production 50%+, building 3 new factories in North Carolina and Texas (3,000+ jobs). NVIDIA received warrants to invest up to $3.2B in Corning shares. GLW stock surged 12%."
    },
    {
      "date": "2026-05-06",
      "type": "news",
      "title": "Corning +12% on NVIDIA Deal; $500M Pre-Funded Warrant Executed; Positioned as Critical AI Data Center Optical Supplier",
      "url": "https://www.cnbc.com/2026/05/06/nvidia-corning-optical-factories-nc-texas-ai.html",
      "source": "CNBC",
      "content": "GLW jumped 12% on NVIDIA partnership. Deal includes $500M pre-funded warrant for NVIDIA to purchase ~3M Corning shares immediately plus additional warrants for up to 15M shares at $180/share — establishing Corning as a cornerstone US-based optical interconnect supplier for AI data centers."
    }
  ],
  "CRDO": [
    {
      "date": "2026-03-01",
      "type": "announcement",
      "title": "Credo Technology Q3 FY2026: Revenue $407M (+201% YoY); Three Hyperscalers >10% Each; AEC Active Cable Ramp Accelerates",
      "url": "https://investors.credosemi.com/news-events/news/news-details/2026/Credo-Technology-Group-Holding-Ltd-Reports-Third-Quarter-of-Fiscal-Year-2026-Financial-Results/default.aspx",
      "source": "Credo Technology IR",
      "content": "Credo Q3 FY2026 (ended Jan 31): revenue $407M surging 201.5% YoY and 51.9% QoQ, non-GAAP GM 68.6%, EPS $1.07. Three hyperscalers each represented >10% of revenue; a fourth beginning material contributions via AEC active cable deployments in AI data centers."
    },
    {
      "date": "2026-05-01",
      "type": "news",
      "title": "Credo Updates Q4 FY2026 Revenue Guidance; Full-Year ~120% YoY Growth on Hyperscaler AEC Expansion and Optical DSP",
      "url": "https://investors.credosemi.com/news-events/news/news-details/2026/Credo-Provides-Preliminary-Third-Quarter-Fiscal-Year-2026-Revenue-Results-Updated-Revenue-Guidance-for-Fourth-Quarter-of-Fiscal-Year-2026-and-Schedules-Third-Quarter-Fiscal-Year-2026-Financial-Results-Conference-Call/default.aspx",
      "source": "Credo Technology IR",
      "content": "Credo updated Q4 FY2026 revenue guidance reiterating ~120% full-year YoY growth, driven by hyperscaler AEC ramps expanding from inter-rack to rack-to-rack use cases plus growing optical DSP and retimer traction. Q4 full results expected late May/early June 2026."
    }
  ],
  "ALAB": [
    {
      "date": "2026-05-05",
      "type": "announcement",
      "title": "Astera Labs Q1 2026: Revenue $308.4M (+93% YoY); Q2 Guided $355-365M — Far Above $310M Street Consensus",
      "url": "https://www.asteralabs.com/news/astera-labs-reports-first-quarter-2026-financial-results/",
      "source": "Astera Labs IR",
      "content": "Astera Labs Q1 2026: revenue $308.4M (+93% YoY), non-GAAP GM 76.4%, EPS $0.61. Q2 guided $355-365M vs $310.3M consensus. Scorpio X-Series (320-lane AI fabric switch) initial volume shipments commenced; PCIe Gen 6 now >1/3 of revenue."
    },
    {
      "date": "2026-05-05",
      "type": "announcement",
      "title": "Astera Labs Scorpio X-Series 320-Lane AI Fabric Switch in Volume Production; On Track to Be Largest Product Line by Year-End",
      "url": "https://futurumgroup.com/insights/astera-labs-q1-fy-2026-earnings-highlight-scale-up-switching-ramp/",
      "source": "Futurum Group",
      "content": "Astera Labs commenced volume shipments of its Scorpio X-Series (320-lane AI fabric switch) in Q1 2026; PCIe Gen 6 solutions exceeding one-third of total revenue. Scorpio on track to become ALAB's largest product line by end of 2026, representing a major diversification from retimers into full AI fabric infrastructure."
    }
  ],
  "CIEN": [
    {
      "date": "2026-03-05",
      "type": "announcement",
      "title": "Ciena Q1 FY2026: Record Revenue $1.43B (+33% YoY); EPS $1.35 Beats by 28%; AI-Driven Optical Demand Broad-Based",
      "url": "https://investor.ciena.com/news-releases/news-release-details/ciena-reports-fiscal-first-quarter-2026-financial-results",
      "source": "Ciena IR",
      "content": "Ciena Q1 FY2026: record revenue $1.43B (+33% YoY), adj EPS $1.35 beat $1.05 estimate by 28.6%, adj GM 44.7%. Demand broad-based across hyperscaler distributed AI training (scale-across), MOFN India growth, and expanding coherent pluggable in-and-around data center opportunities. Next earnings Q2 FY2026 scheduled June 4."
    }
  ],
  "CSCO": [
    {
      "date": "2026-02-12",
      "type": "announcement",
      "title": "Cisco Q2 FY2026: $2.1B AI Infrastructure Orders in One Quarter (= All of FY2025); Full-Year AI Outlook Raised to >$5B",
      "url": "https://investor.cisco.com/news/news-details/2026/CISCO-REPORTS-SECOND-QUARTER-EARNINGS/default.aspx",
      "source": "Cisco IR",
      "content": "Cisco Q2 FY2026: $2.1B in AI infrastructure orders in a single quarter — equal to all of FY2025 combined — raising full-year AI infrastructure order outlook to >$5B. Silicon One ASIC adoption and data center networking demand driving acceleration. Splunk added 500 new logos in H1 FY26. Q3 FY2026 results scheduled May 13."
    }
  ],
  "PWR": [
    {
      "date": "2026-05-07",
      "type": "announcement",
      "title": "Quanta Services Q1 2026: Record Revenue $7.87B (+26% YoY); Backlog $48.5B; Raises Full-Year Guide to $34.7-35.2B",
      "url": "https://investors.quantaservices.com/news-events/press-releases/detail/396/quanta-services-reports-first-quarter-2026-results",
      "source": "Quanta Services IR",
      "content": "Quanta Services Q1 2026: record revenue $7.87B (+26% YoY), adj EPS $2.68 vs $1.78 a year ago, record backlog $48.5B. Raised FY2026 revenue guidance to $34.7-35.2B and adj EPS to $13.55-14.25. Data center grid connection and power transmission line construction driving strong demand."
    }
  ],
  "EME": [
    {
      "date": "2026-04-29",
      "type": "announcement",
      "title": "EMCOR Q1 2026: Record Revenue $4.63B (+20% YoY); Data Center Electrical Revenues +~50%; Raises Full-Year Guide to $18.5-19.25B",
      "url": "https://markets.financialcontent.com/stocks/article/stockstory-2026-4-29-emcor-nyseeme-surprises-with-strong-q1-cy2026",
      "source": "FinancialContent / StockStory",
      "content": "EMCOR Q1 2026: revenue $4.63B (+19.7% YoY), EPS $6.84 (+30%), beat consensus EPS by 16.9% and revenue by 9.7%. Network & Communications (data center electrical) revenues surged ~50%. Raised FY2026 revenue guidance to $18.5-19.25B and adj EPS to $28.25-29.75."
    }
  ],
  "FIX": [
    {
      "date": "2026-04-24",
      "type": "announcement",
      "title": "Comfort Systems Q1 2026: Revenue +56% to $2.9B; EPS Beats by 55%; Record GM 26.3%; Backlog $12.45B; Full-Year Guide $10.93B",
      "url": "https://seekingalpha.com/news/4579638-comfort-systems-forecasts-mid-to-high-20-percent-2026-same-store-revenue-growth-as-backlog",
      "source": "Seeking Alpha",
      "content": "Comfort Systems Q1 2026: EPS $10.51 beat estimates by 55%; revenue $2.9B beat by ~21%; same-store revenue +51% driven by data center HVAC construction demand; gross margin all-time high 26.3%. Backlog $12.45B; guided FY2026 revenue to $10.93B with mid-to-high 20% same-store growth."
    }
  ],
  "MOD": [
    {
      "date": "2026-02-04",
      "type": "announcement",
      "title": "Modine Manufacturing Q3 FY2026: Data Center Cooling Sales +78% YoY; Raises FY2026 Guide to 40-45% Climate Solutions Growth",
      "url": "https://investors.modine.com/news/news-details/2026/Modine-Reports-Third-Quarter-Fiscal-2026-Results/default.aspx",
      "source": "Modine Manufacturing IR",
      "content": "Modine Q3 FY2026 (ended Dec 31, 2025): net sales +31% YoY to $805M; data center cooling +78% YoY. Four new chiller production lines commissioned with four more planned Q4. Raised FY2026 guidance to Climate Solutions growth 40-45% and total data center sales >70% growth. Q4 FY2026 (fiscal year end Mar 31) results due May 22, 2026."
    }
  ],
  "TT": [
    {
      "date": "2026-04-30",
      "type": "announcement",
      "title": "Trane Technologies Q1 2026: Revenue $4.97B Beat; Acquires Stellar Energy (Data Center Cooling) for $553M; Raises Full-Year Guide",
      "url": "https://investors.tranetechnologies.com/news-and-events/news-releases/news-release-details/2026/Trane-Technologies-Reports-Strong-First-Quarter-Results-Raises-Full-Year-Revenue-and-EPS-Guidance/default.aspx",
      "source": "Trane Technologies IR",
      "content": "Trane Q1 2026: revenue $4.97B beat $4.81B estimate; adj EPS $2.63 topped $2.53; Americas Commercial HVAC bookings +~40%; record backlog $10.7B (+30%+ from year-end). Acquired data center cooling provider Stellar Energy for ~$553M. Raised FY2026 revenue growth guidance to ~9.5%, adj EPS $14.75-14.95."
    }
  ],
  "JCI": [
    {
      "date": "2026-05-06",
      "type": "announcement",
      "title": "Johnson Controls Q2 FY2026: Orders +30%; Record Backlog $20B; Adj EPS +45% to $1.19; Raises FY2026 Guidance",
      "url": "https://www.prnewswire.com/news-releases/johnson-controls-reports-strong-q2-results-raises-fy26-guidance-302763526.html",
      "source": "PR Newswire / Johnson Controls IR",
      "content": "JCI Q2 FY2026: sales +8% to $6.1B (organic +6%), adj EPS $1.19 (+45% YoY); orders +30% with record $20B backlog driven by data center and technology demand. Raised FY2026 guidance to ~6% organic sales growth and adj EPS ~$4.85."
    }
  ],
  "NRG": [
    {
      "date": "2026-05-06",
      "type": "announcement",
      "title": "NRG Energy Q1 2026: Revenue $10.26B Post-LS Power Acquisition; EPS $1.49 Misses $2.78 Estimate on Texas Weather Costs",
      "url": "https://www.investing.com/news/transcripts/earnings-call-transcript-nrg-energys-q1-2026-results-miss-eps-forecasts-stock-dips-93CH-4664273",
      "source": "Investing.com",
      "content": "NRG Q1 2026: revenue $10.26B (from $8.59B) following January close of ~$13B LS Power acquisition (13GW gas generation). EPS $1.49 missed $2.78 consensus due to mild Texas weather and Winter Storm Fern supply costs. Reaffirmed 2026 guidance; announced $1B share buyback."
    },
    {
      "date": "2026-05-06",
      "type": "announcement",
      "title": "NRG Energy Signs Long-Term 295MW Power Deal for Two Texas AI Data Centers on Company-Owned Sites",
      "url": "https://www.datacenterdynamics.com/en/news/nrg-signs-295mw-power-supply-deal-for-two-data-centers-in-texas/",
      "source": "Data Center Dynamics",
      "content": "NRG signed a long-term 295MW power supply agreement serving two data centers on company-owned Texas sites, part of its strategy to monetize the expanded post-LS Power generation fleet for AI data center demand growth."
    }
  ],
  "KMI": [
    {
      "date": "2026-04-22",
      "type": "announcement",
      "title": "Kinder Morgan Q1 2026: EPS +41% to $0.48; Acquires Monument Pipeline for $505M; Moody's Upgrades to Baa1",
      "url": "https://ir.kindermorgan.com/news/news-details/2026/Kinder-Morgan-Reports-First-Quarter-2026-Financial-Results/default.aspx",
      "source": "Kinder Morgan IR",
      "content": "KMI Q1 2026: adj EPS +41% YoY to $0.48, revenue +13.8% to $4.83B. Announced and closed $505M acquisition of Monument Pipeline (225-mile Houston-area system) on May 1. Moody's upgraded to Baa1. Long take-or-pay contracts expand Texas intrastate gas network supporting data center generation."
    }
  ],
  "WMB": [
    {
      "date": "2026-05-04",
      "type": "announcement",
      "title": "Williams Companies Q1 2026: Record Adj EBITDA $2.25B (+13% YoY); Raises Growth CapEx to $7.3B; Dividend +5%",
      "url": "https://www.williams.com/2026/05/04/williams-announces-record-first-quarter-2026-results/",
      "source": "Williams Companies",
      "content": "Williams Q1 2026: record adj EBITDA $2.25B (+13% YoY), adj EPS $0.73 beat $0.65 consensus. Deepwater Gulf EBITDA +60%+, Natural Gas Storage +35%. Raised growth CapEx midpoint to $7.3B; increased annualized dividend 5% to $2.10/share. Reaffirmed 2026 EBITDA guidance $8.05-8.35B."
    }
  ],
  "ASE": [
    {
      "date": "2026-04-29",
      "type": "announcement",
      "title": "ASE Technology Q1 2026: Revenue +17.2% YoY to NT$173.7B (~$5.44B); ATM Segment +29.7%; Net Income Nearly Doubles",
      "url": "https://finance.yahoo.com/markets/stocks/articles/ase-technology-holding-co-asx-180355621.html",
      "source": "Yahoo Finance",
      "content": "ASE Technology Q1 2026: net revenues +17.2% YoY to NT$173.7B (~$5.44B USD). ATM (assembly, testing, materials) +29.7% YoY; net income nearly doubled to NT$14.1B. Gross margin +3.3 pp YoY to 20.1%. Advanced packaging (CoWoS/SoIC) demand driving growth. ADR shares rose ~3.4% premarket."
    }
  ],
  "AMKR": [
    {
      "date": "2026-04-27",
      "type": "announcement",
      "title": "Amkor Technology Q1 2026: Record Revenue $1.685B (+27% YoY); EPS $0.33 Beats by 50%; Q2 Guided $1.75-1.85B",
      "url": "https://ir.amkor.com/news-releases/news-release-details/amkor-technology-reports-financial-results-first-quarter-2026",
      "source": "Amkor Technology IR",
      "content": "Amkor Q1 2026: record net sales $1.685B (+27% YoY), EPS $0.33 beat $0.22 consensus by 50% on broad-based demand and advanced packaging (2.5D/3D) strength. Q2 guided $1.75-1.85B with EPS $0.42-0.52. Full-year capex $2.5-3.0B for capacity expansion. Stock fell ~9% AH despite the beat."
    }
  ],
  "TER": [
    {
      "date": "2026-04-28",
      "type": "announcement",
      "title": "Teradyne Q1 2026: Record Revenue $1.282B (+87% YoY); ~70% AI-Related Demand (HBM/SoC Test); Q2 Guided $1.15-1.25B",
      "url": "https://investors.teradyne.com/news-events/press-releases/detail/440/teradyne-reports-first-quarter-2026-results",
      "source": "Teradyne IR",
      "content": "Teradyne Q1 2026: record revenue $1.282B surging 87% YoY with ~70% of revenues tied to AI-related demand for HBM and SoC test equipment. Non-GAAP EPS $2.56 beat $2.12 estimate by $0.44. Q2 guided $1.15-1.25B revenue and non-GAAP EPS $1.86-2.15."
    }
  ],
  "NOW": [
    {
      "date": "2026-04-22",
      "type": "announcement",
      "title": "ServiceNow Q1 2026: Revenue +22%; Now Assist ACV Target Raised to $1.5B; Stock Falls 14-17% on Iran War Deal Delay Disclosure",
      "url": "https://newsroom.servicenow.com/press-releases/details/2026/ServiceNow-Reports-First-Quarter-2026-Financial-Results/default.aspx",
      "source": "ServiceNow Newsroom / CNBC",
      "content": "ServiceNow Q1 2026: subscription revenue $3.67B (+22% YoY); raised FY2026 subscription revenue guidance by $205M to $15.735-15.775B; Now Assist ACV target raised $1B to $1.5B. Stock fell 14-17% on disclosure of ~75bps headwind from delayed large on-premise deals in the Middle East due to the Iran war."
    }
  ]
};

let totalAdded = 0;

for (const [ticker, items] of Object.entries(additions)) {
  if (!data[ticker]) data[ticker] = [];
  const existingUrls = new Set(data[ticker].map(i => i.url));
  const existingTitles = new Set(data[ticker].map(i => i.title));

  for (const item of items) {
    if (!existingUrls.has(item.url) && !existingTitles.has(item.title)) {
      data[ticker].push(item);
      existingUrls.add(item.url);
      existingTitles.add(item.title);
      totalAdded++;
    }
  }
}

fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
console.log(`Done. Added ${totalAdded} new items.`);
