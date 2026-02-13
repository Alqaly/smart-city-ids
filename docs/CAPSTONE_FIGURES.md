# Capstone Report — Figures & Diagrams

> **20 Mermaid diagrams** ready to embed in your capstone report.
> Each figure includes its chapter reference and a Mermaid code block.
> To render: paste each code block into any Mermaid-compatible tool (GitHub Markdown, Mermaid Live Editor, VS Code preview, LaTeX with mermaid-filter, etc.).

---

## Table of Figures

| #  | Title | Report Section |
|----|-------|----------------|
| 1  | High-Level System Architecture | §4.2 System Architecture |
| 2  | Alert Processing Pipeline (Sequence) | §4.3 Algorithm Design |
| 3  | IoT Device Integration Paths | §5.5 IoT Service Design |
| 4  | LLM Multi-Provider Failover Chain | §5.2 Multi-LLM Engine |
| 5  | HITL Governance Modes State Machine | §5.3 Human-in-the-Loop |
| 6  | Kubernetes Cluster Topology | §5.4 Kubernetes Automation |
| 7  | Attack Scenario Severity Distribution | §6.4 Attack Simulation |
| 8  | Alert Volume Reduction Funnel | §5.6 Deduplication Engine |
| 9  | Circuit Breaker State Machine | §5.2 Multi-LLM Engine |
| 10 | Technology Stack Layer Diagram | §4.5 Technology Stack |
| 11 | Project Timeline (Gantt) | §4.6 Work Breakdown Structure |
| 12 | Deduplication Decision Tree | §5.6 Deduplication Engine |
| 13 | Raspberry Pi Network Path | §5.5 IoT Service Design |
| 14 | IoT Device Distribution by Type | §5.5 IoT Service Design |
| 15 | FHIR R4 Resource Hierarchy | §5.5 IoT Service Design |
| 16 | Severity-Based Automated Response Matrix | §5.4 Kubernetes Automation |
| 17 | MITRE ATT&CK for ICS Technique Map | §6.4 Attack Simulation |
| 18 | IoT SDK Integration Steps | §5.5 IoT Service Design |
| 19 | Before vs After: Manual vs AI-Driven Response | §6.5 Performance Metrics |
| 20 | Cluster Scalability & Resource Headroom | §6.5 Performance Metrics |

---

## Chapter 4 — Design & Methodology

### Figure 1 — High-Level System Architecture
**Reference:** §4.2 System Architecture

```mermaid
graph TB
    subgraph IoT["IoT Device Layer"]
        TC["Traffic Camera\nONVIF XML"]
        PS["Parking Sensor\nMQTT / CoAP"]
        HA["Healthcare API\nFHIR R4 JSON"]
        ES["Environmental Sensor\nModbus / OPC UA"]
        SL["Street Lighting\nDALI-2 / TALQ"]
    end

    subgraph Detection["Detection Layer"]
        F["Falco\nRuntime Security"]
        S["Suricata\nNetwork IDS"]
    end

    subgraph Core["IDS Core (FastAPI)"]
        FW["Forwarder\nAlert Ingestion"]
        DD["Dedup Engine\n85-95% reduction"]
        LLM["Multi-LLM Analyzer\n6 providers"]
        HITL["HITL Governance\n3 modes"]
        AUTO["K8s Automator\nIsolate / Scale"]
    end

    subgraph K8s["Kubernetes (K3s)"]
        API["K8s API Server"]
        PODS["34 Running Pods"]
    end

    subgraph UI["Operator Interface"]
        DASH["Security Analyst\nDashboard"]
        SSE["SSE Live Feed"]
    end

    IoT -->|Telemetry + Alerts| Detection
    Detection -->|JSON Alerts| FW
    FW --> DD --> LLM --> HITL --> AUTO
    AUTO -->|kubectl| API --> PODS
    Core -->|Events| SSE --> DASH
    DASH -->|Actions| Core

    style Core fill:#1a1a2e,color:#00d4ff
    style IoT fill:#0d1b2a,color:#e0e0e0
    style Detection fill:#1b2838,color:#ff6b6b
    style K8s fill:#162447,color:#00d4ff
    style UI fill:#1a1a2e,color:#e94560
```

---

### Figure 2 — Alert Processing Pipeline (Sequence Diagram)
**Reference:** §4.3 Algorithm Design

```mermaid
sequenceDiagram
    participant F as Falco / Suricata
    participant FW as Forwarder
    participant DD as Dedup Engine
    participant LLM as Multi-LLM Analyzer
    participant HITL as HITL Governor
    participant K8s as K8s Automator
    participant DB as Alert Store
    participant UI as Dashboard (SSE)

    F->>FW: Raw alert JSON
    FW->>DD: Normalized alert
    DD->>DD: Hash check (85-95% filtered)
    alt New unique alert
        DD->>LLM: Analyze threat
        LLM->>LLM: Try Provider 1 → 2 → … → Fallback
        LLM-->>HITL: {severity, threat_type, recommendations}
        alt Autopilot Mode
            HITL->>K8s: Execute automated_actions
            K8s->>K8s: isolate_pod / scale_up
        else Assisted Mode
            HITL-->>UI: Request analyst approval
            UI->>K8s: Analyst confirms action
        else Manual Mode
            HITL-->>UI: Log only — no automation
        end
    else Duplicate
        DD-->>DB: Increment count, skip LLM
    end
    K8s-->>DB: Store result
    DB-->>UI: SSE push event
```

---

### Figure 10 — Technology Stack Layer Diagram
**Reference:** §4.5 Technology Stack

```mermaid
graph TB
    subgraph L8["Layer 8 — Operator Interface"]
        D1["Security Analyst Dashboard\n7 interactive tabs"]
        D2["SSE Live Feed\nReal-time events"]
    end

    subgraph L7["Layer 7 — AI / LLM"]
        A1["xAI Grok-4"]
        A2["OpenAI GPT-4"]
        A3["Anthropic Claude"]
        A4["Google Gemini"]
        A5["Moonshot Kimi"]
        A6["Local Fallback"]
    end

    subgraph L6["Layer 6 — Application"]
        B1["FastAPI IDS Core\nPython 3.11"]
        B2["Dedup Engine"]
        B3["HITL Governance"]
    end

    subgraph L5["Layer 5 — Security"]
        C1["Falco\nRuntime"]
        C2["Suricata\nNetwork"]
    end

    subgraph L4["Layer 4 — Orchestration"]
        E1["K3s (Kubernetes)\nSingle-node cluster"]
    end

    subgraph L3["Layer 3 — IoT Emulation"]
        F1["5 Protocol Emulators\nONVIF, MQTT, FHIR, Modbus, DALI"]
    end

    subgraph L2["Layer 2 — Infrastructure"]
        G1["Ubuntu 24.04 VM\n4 vCPU / 8 GB RAM"]
    end

    subgraph L1["Layer 1 — Hardware Edge"]
        H1["Raspberry Pi 4\nDS18B20 / DHT22"]
    end

    L8 --> L7 --> L6 --> L5 --> L4 --> L3 --> L2 --> L1

    style L8 fill:#e94560,color:#fff
    style L7 fill:#a855f7,color:#fff
    style L6 fill:#00d4ff,color:#000
    style L5 fill:#ef4444,color:#fff
    style L4 fill:#1e40af,color:#fff
    style L3 fill:#22c55e,color:#000
    style L2 fill:#64748b,color:#fff
    style L1 fill:#d97706,color:#000
```

---

### Figure 11 — Project Timeline (Gantt Chart)
**Reference:** §4.6 Work Breakdown Structure

```mermaid
gantt
    title Smart City IDS — Project Timeline
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d

    section Research
    Literature Review           :done, r1, 2025-01-15, 21d
    Requirements Analysis       :done, r2, after r1, 14d

    section Core Platform
    K3s Cluster Setup           :done, c1, 2025-02-19, 7d
    IDS API (FastAPI)           :done, c2, after c1, 14d
    Falco Integration           :done, c3, after c2, 7d

    section AI Integration
    LLM Engine (xAI)            :done, a1, 2025-03-19, 10d
    Multi-Provider Failover     :done, a2, after a1, 7d
    HITL Governance             :done, a3, after a2, 7d

    section IoT & Attacks
    5 IoT Emulators             :done, i1, 2025-04-09, 14d
    12 Attack Scenarios          :done, i2, after i1, 7d
    Raspberry Pi HW             :done, i3, after i1, 7d

    section Polish
    Dashboard (7 tabs)          :done, p1, 2025-05-07, 10d
    Dedup & Circuit Breaker     :done, p2, after p1, 5d
    Documentation & Report      :active, p3, after p2, 14d
```

---

## Chapter 5 — Implementation

### Figure 3 — IoT Device Integration Paths
**Reference:** §5.5 IoT Service Design

```mermaid
graph LR
    subgraph HW["Path 1 — Physical Hardware"]
        RPI["Raspberry Pi 4\nDS18B20 sensor"] -->|HTTP POST\nport-forwarded| IDS1["IDS API\n:30800"]
    end

    subgraph K8S["Path 2 — K8s Emulators"]
        EMU["5 IoT Emulators\nConfigMap-mounted"] -->|ClusterIP\ninternal traffic| IDS2["IDS API\n:8000"]
    end

    subgraph ATK["Path 3 — Attack Simulator"]
        SIM["12 Attack Scenarios\nDashboard console"] -->|POST /api/alerts\nJSON payload| IDS3["IDS API\n:30800"]
    end

    IDS1 --> CORE["Alert Pipeline\nDedup → LLM → HITL → K8s"]
    IDS2 --> CORE
    IDS3 --> CORE

    style HW fill:#d97706,color:#000
    style K8S fill:#1e40af,color:#fff
    style ATK fill:#ef4444,color:#fff
    style CORE fill:#00d4ff,color:#000
```

---

### Figure 4 — LLM Multi-Provider Failover Chain
**Reference:** §5.2 Multi-LLM Engine

```mermaid
graph LR
    A["Incoming\nAlert"] --> P1{"xAI\nGrok-4"}
    P1 -->|Success| R["Return\nAnalysis"]
    P1 -->|Fail / Timeout| P2{"OpenAI\nGPT-4"}
    P2 -->|Success| R
    P2 -->|Fail / Timeout| P3{"Anthropic\nClaude"}
    P3 -->|Success| R
    P3 -->|Fail / Timeout| P4{"Google\nGemini"}
    P4 -->|Success| R
    P4 -->|Fail / Timeout| P5{"Moonshot\nKimi"}
    P5 -->|Success| R
    P5 -->|Fail / Timeout| P6["Local\nFallback\nEngine"]
    P6 -->|Always succeeds| R
    R --> CB["Circuit Breaker\nper provider\n5-fail threshold"]

    style P1 fill:#a855f7,color:#fff
    style P2 fill:#22c55e,color:#000
    style P3 fill:#d97706,color:#fff
    style P4 fill:#1e40af,color:#fff
    style P5 fill:#ef4444,color:#fff
    style P6 fill:#64748b,color:#fff
    style CB fill:#991b1b,color:#fff
```

---

### Figure 5 — HITL Governance Modes State Machine
**Reference:** §5.3 Human-in-the-Loop Governance

```mermaid
stateDiagram-v2
    [*] --> Autopilot : Default startup

    Autopilot --> Assisted : Analyst selects Assisted
    Autopilot --> Manual : Analyst selects Manual

    Assisted --> Autopilot : Analyst selects Autopilot
    Assisted --> Manual : Analyst selects Manual

    Manual --> Autopilot : Analyst selects Autopilot
    Manual --> Assisted : Analyst selects Assisted

    state Autopilot {
        [*] --> AutoExec
        AutoExec : severity >= 8 → isolate pod
        AutoExec : severity >= 6 → scale up
        AutoExec : severity < 6 → log only
    }

    state Assisted {
        [*] --> ProposeAction
        ProposeAction : LLM recommends action
        ProposeAction --> AwaitApproval
        AwaitApproval : Analyst approves / rejects
        AwaitApproval --> Execute : Approved
        AwaitApproval --> LogOnly : Rejected
    }

    state Manual {
        [*] --> LogAndAlert
        LogAndAlert : No automated actions
        LogAndAlert : Analyst acts manually
    }
```

---

### Figure 6 — Kubernetes Cluster Topology
**Reference:** §5.4 Kubernetes Automation

```mermaid
graph TB
    subgraph Node["K3s Node — capstone (Ubuntu 24.04)"]
        subgraph NS["Namespace: smart-city"]
            IDS["IDS API ×2\nFastAPI :8000"]
            TC["Traffic Camera ×3\nONVIF XML"]
            PS["Parking System ×3\nMQTT/CoAP"]
            HC["Healthcare API ×3\nFHIR R4"]
            ENV["Env Sensor ×2\nModbus/OPC UA"]
            SL["Street Light ×2\nDALI-2/TALQ"]
            FW["Falco Forwarder ×2"]
            SW["Suricata Forwarder ×2"]
            GF["Grafana ×1"]
            MQTT["MQTT Broker ×1"]
            AR["Attack Receiver ×1"]
        end
        subgraph SYS["System Namespaces"]
            FALCO["Falco DaemonSet\n(falco-system)"]
            SURI["Suricata DaemonSet\n(suricata)"]
            KUBE["kube-system pods ×8"]
        end
    end

    IDS -->|NodePort 30800| EXT["External\nTraffic"]
    FALCO -->|Alerts| FW -->|POST| IDS
    SURI -->|Alerts| SW -->|POST| IDS
    TC & PS & HC & ENV & SL -->|Telemetry| IDS

    style Node fill:#0d1b2a,color:#e0e0e0
    style NS fill:#1a1a2e,color:#00d4ff
    style SYS fill:#162447,color:#ff6b6b
    style IDS fill:#00d4ff,color:#000
```

---

### Figure 9 — Circuit Breaker State Machine
**Reference:** §5.2 Multi-LLM Engine

```mermaid
stateDiagram-v2
    [*] --> Closed

    Closed --> Open : failure_count >= 5
    Closed --> Closed : success (reset counter)

    Open --> HalfOpen : cooldown_period expires (60s)

    HalfOpen --> Closed : probe succeeds
    HalfOpen --> Open : probe fails

    state Closed {
        [*] --> Healthy
        Healthy : All requests forwarded
        Healthy : failure_count tracks errors
    }

    state Open {
        [*] --> Blocked
        Blocked : All requests rejected
        Blocked : Timer: 60s cooldown
        Blocked : Failover to next provider
    }

    state HalfOpen {
        [*] --> Probing
        Probing : Single test request sent
        Probing : Success → reset to Closed
        Probing : Failure → back to Open
    }
```

---

### Figure 8 — Alert Volume Reduction Funnel
**Reference:** §5.6 Deduplication Engine

```mermaid
graph TB
    A["Raw Alerts\n~10,000 / hour\nfrom Falco + Suricata"] --> B["Hash-Based Dedup\nSHA-256 fingerprint\n~60% filtered"]
    B --> C["Similarity Window\ntime-bucketed grouping\n~25% more filtered"]
    C --> D["Priority Filter\nseverity < threshold skipped\n~5% more filtered"]
    D --> E["Unique Alerts\n500–1,000 / hour\nSent to LLM"]
    E --> F["LLM Analysis\n~3s per alert\n6-provider failover"]
    F --> G["Automated Actions\nisolate / scale / log"]

    style A fill:#ef4444,color:#fff
    style B fill:#f97316,color:#fff
    style C fill:#eab308,color:#000
    style D fill:#84cc16,color:#000
    style E fill:#22c55e,color:#000
    style F fill:#a855f7,color:#fff
    style G fill:#00d4ff,color:#000
```

---

### Figure 12 — Deduplication Decision Tree
**Reference:** §5.6 Deduplication Engine

```mermaid
graph TD
    START["New Alert Arrives"] --> HASH{"Compute SHA-256\nhash of\n(rule + container + cmd)"}
    HASH --> CHECK{"Hash exists\nin cache?"}
    CHECK -->|No| WINDOW{"Within time\nwindow of\nsimilar alert?"}
    CHECK -->|Yes| DUP["DUPLICATE\nIncrement counter\nSkip LLM"]
    WINDOW -->|No| PRIORITY{"Severity\n>= threshold?"}
    WINDOW -->|Yes| MERGE["MERGE\nGroup with existing\nUpdate timestamp"]
    PRIORITY -->|Yes| LLM["UNIQUE → Send to LLM\nfor full analysis"]
    PRIORITY -->|No| LOW["LOW PRIORITY\nLog only\nSkip LLM"]
    LLM --> CACHE["Add hash to cache\nTTL = 5 min"]

    style DUP fill:#ef4444,color:#fff
    style MERGE fill:#eab308,color:#000
    style LOW fill:#64748b,color:#fff
    style LLM fill:#22c55e,color:#000
    style CACHE fill:#00d4ff,color:#000
```

---

### Figure 13 — Raspberry Pi Network Path
**Reference:** §5.5 IoT Service Design

```mermaid
graph LR
    subgraph RPi["Raspberry Pi 4 (192.168.1.x)"]
        SENSOR["DS18B20\nTemperature\nSensor"]
        SCRIPT["device_template.py\nSmartCityDevice\nsubclass"]
        SENSOR -->|GPIO / 1-Wire| SCRIPT
    end

    subgraph Win["Windows Host (Port Proxy)"]
        PROXY["netsh portproxy\n0.0.0.0:30800 →\n172.x.x.x:30800"]
    end

    subgraph VM["Ubuntu 24.04 VM (K3s)"]
        NP["NodePort :30800"]
        IDS["IDS API\nFastAPI :8000"]
        NP --> IDS
    end

    SCRIPT -->|HTTP POST\nJSON alert| PROXY
    PROXY -->|Forward| NP

    style RPi fill:#d97706,color:#000
    style Win fill:#1e40af,color:#fff
    style VM fill:#22c55e,color:#000
```

---

### Figure 14 — IoT Device Distribution by Type
**Reference:** §5.5 IoT Service Design

```mermaid
pie title Emulated IoT Device Fleet (620 virtual devices)
    "Smart Parking Sensors (MQTT/CoAP)" : 450
    "Street Lighting Controllers (DALI-2)" : 120
    "Medical Devices (FHIR R4)" : 100
    "Environmental Sensors (Modbus)" : 80
    "Traffic Cameras (ONVIF)" : 8
```

---

### Figure 15 — FHIR R4 Resource Hierarchy
**Reference:** §5.5 IoT Service Design

```mermaid
classDiagram
    class Patient {
        +id: string
        +name: HumanName[]
        +birthDate: date
        +gender: code
    }
    class Observation {
        +id: string
        +status: code
        +code: CodeableConcept
        +valueQuantity: Quantity
        +effectiveDateTime: dateTime
        +subject: Reference~Patient~
    }
    class MedicationRequest {
        +id: string
        +status: code
        +medicationCodeableConcept: CodeableConcept
        +subject: Reference~Patient~
        +dosageInstruction: Dosage[]
    }
    class Device {
        +id: string
        +status: code
        +type: CodeableConcept
        +patient: Reference~Patient~
        +serialNumber: string
    }
    class Bundle {
        +id: string
        +type: code
        +entry: BundleEntry[]
        +total: unsignedInt
    }

    Patient "1" --> "*" Observation : subject
    Patient "1" --> "*" MedicationRequest : subject
    Patient "1" --> "*" Device : patient
    Bundle "1" --> "*" Patient : entry
    Bundle "1" --> "*" Observation : entry
```

---

### Figure 16 — Severity-Based Automated Response Matrix
**Reference:** §5.4 Kubernetes Automation

```mermaid
graph LR
    subgraph Auto["Automated Response Actions"]
        direction TB
        S10["Severity 10\nRansomware / Data Tamper"] --> A10["🔴 ISOLATE POD\n+ Alert Analyst\n+ Collect Forensics"]
        S8["Severity 8-9\nDDoS / Shell / Hijack"] --> A8["🟠 ISOLATE POD\n+ Scale Service Up"]
        S6["Severity 6-7\nRecon / Exfil / Spoof"] --> A6["🟡 SCALE UP\n+ Log Warning"]
        S4["Severity 4-5\nLow Confidence"] --> A4["🟢 LOG ONLY\n+ Add to Audit"]
    end

    style S10 fill:#991b1b,color:#fff
    style S8 fill:#ef4444,color:#fff
    style S6 fill:#eab308,color:#000
    style S4 fill:#22c55e,color:#000
    style A10 fill:#991b1b,color:#fff
    style A8 fill:#ef4444,color:#fff
    style A6 fill:#eab308,color:#000
    style A4 fill:#22c55e,color:#000
```

---

### Figure 18 — IoT SDK Integration Steps
**Reference:** §5.5 IoT Service Design

```mermaid
graph TB
    subgraph SDK["IoT SDK Integration Pattern"]
        direction TB
        T1["1. Copy device_template.py"] --> T2["2. Subclass SmartCityDevice"]
        T2 --> T3["3. Override read_sensor()"]
        T3 --> T4["4. Override is_anomaly()"]
        T4 --> T5{"Deploy where?"}
        T5 -->|Hardware| T6["5a. Run on RPi/Edge\npython3 my_sensor.py\n--ids-url http://..."]
        T5 -->|Kubernetes| T7["5b. Create ConfigMap\n+ Deployment YAML"]
        T6 --> T8["6. Register in main.py\n_IOT_SERVICES dict"]
        T7 --> T8
        T8 --> T9["7. Add Dashboard Card\nindex.html IoT tab"]
    end

    style T1 fill:#00d4ff,color:#000
    style T9 fill:#22c55e,color:#000
```

---

## Chapter 6 — Testing & Results

### Figure 7 — Attack Scenario Severity Distribution
**Reference:** §6.4 Attack Simulation

```mermaid
pie title 12 Attack Scenarios by Severity
    "Critical (9-10)" : 4
    "High (7-8)" : 5
    "Medium (5-6)" : 2
    "Low (3-4)" : 1
```

---

### Figure 17 — MITRE ATT&CK for ICS Technique Map
**Reference:** §6.4 Attack Simulation

```mermaid
graph TB
    subgraph MITRE["MITRE ATT&CK for ICS — Coverage Map"]
        direction TB
        IA["Initial Access"] --- T866["T0866\nExploitation of\nRemote Services"]
        EX["Execution"] --- T807["T0807\nCommand-Line\nInterface"]
        DIS["Discovery"] --- T846["T0846\nRemote System\nDiscovery"]
        LM["Lateral Movement"] --- T867["T0867\nLateral Tool\nTransfer"]
        COL["Collection"] --- T859["T0859\nValid Accounts"]
        EVA["Evasion"] --- T856["T0856\nSpoof Reporting\nMessage"]
        IMP["Impair Process"] --- T836["T0836\nModify Parameter"]
        IMP --- T855["T0855\nUnauthorized\nCommand Message"]
        IMPACT["Impact"] --- T831["T0831\nManipulation\nof Control"]
        IMPACT --- T830["T0830\nMan in the\nMiddle"]
        IMPACT --- T828["T0828\nLoss of\nProductivity"]
        EXFIL["Exfiltration"] --- T882["T0882\nTheft of\nOperational Info"]
    end

    style IA fill:#ef4444,color:#fff
    style EX fill:#f97316,color:#fff
    style DIS fill:#eab308,color:#000
    style LM fill:#a855f7,color:#fff
    style COL fill:#d97706,color:#000
    style EVA fill:#6366f1,color:#fff
    style IMP fill:#ec4899,color:#fff
    style IMPACT fill:#991b1b,color:#fff
    style EXFIL fill:#00d4ff,color:#000
```

---

### Figure 19 — Before vs After: Manual vs AI-Driven Response
**Reference:** §6.5 Performance Metrics

```mermaid
graph LR
    subgraph Before["BEFORE — Manual Monitoring"]
        direction TB
        B1["Sysadmin reads\nraw Falco JSON"] --> B2["Manual severity\nassessment"]
        B2 --> B3["Google threat\nintelligence"]
        B3 --> B4["SSH to node\nkubectl manually"]
        B4 --> B5["~15 min avg\nresponse time"]
    end

    subgraph After["AFTER — AI-Driven IDS"]
        direction TB
        A1["Falco alert\nauto-forwarded"] --> A2["LLM severity\nanalysis < 3s"]
        A2 --> A3["Contextual threat\nintel + recommendations"]
        A3 --> A4["Auto pod isolation\n/ scale-up"]
        A4 --> A5["< 5 sec avg\nresponse time"]
    end

    Before -.->|"180x faster"| After

    style B5 fill:#ef4444,color:#fff
    style A5 fill:#22c55e,color:#000
    style Before fill:#fef3c7,color:#000
    style After fill:#d1fae5,color:#000
```

---

### Figure 20 — Cluster Scalability & Resource Headroom
**Reference:** §6.5 Performance Metrics

```mermaid
graph TB
    subgraph Scale["Scalability & Resource Allocation"]
        direction TB
        R1["K3s Single Node\n4 vCPU / 8 GB RAM"]
        R1 --> R2["34 Running Pods"]
        R2 --> R3["CPU: 17% utilised\n(680m / 4000m)"]
        R2 --> R4["Memory: 76% utilised\n(6.1 GB / 8 GB)"]
        R3 --> R5["Headroom: +83% CPU\nfor burst scaling"]
        R4 --> R6["Headroom: +24% MEM\nfor ~10 more pods"]
        R5 --> R7["Estimated Max:\n~44 pods @ 4 vCPU"]
        R6 --> R7
    end

    style R1 fill:#1e40af,color:#fff
    style R2 fill:#00d4ff,color:#000
    style R3 fill:#22c55e,color:#000
    style R4 fill:#eab308,color:#000
    style R7 fill:#a855f7,color:#fff
```

---

## How to Use These Figures

### In Markdown / GitHub
Paste the Mermaid code blocks directly — GitHub renders them natively.

### In LaTeX
Use the [mermaid-filter](https://github.com/raghur/mermaid-filter) Pandoc filter or export each diagram as PNG/SVG from [Mermaid Live Editor](https://mermaid.live) and include with `\includegraphics`.

### In Word / PowerPoint
1. Go to [mermaid.live](https://mermaid.live)
2. Paste the Mermaid code
3. Download as PNG or SVG
4. Insert into your document

### Recommended Captioning
Use IEEE-style captions:
```
Figure X: <Title> — <brief description of what the diagram shows>
```
