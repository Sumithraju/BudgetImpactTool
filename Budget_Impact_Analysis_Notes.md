# Budget Impact Estimation Tool & Market Access Notes

## 1. Project Overview & Problem Statement
* **Context**: Early-stage Budget Impact Estimation Tool for Pricing & Market Access (e.g., when Novo Nordisk develops a new diabetes or obesity drug).
* **Key Questions Before Launch**:
  1. How much will it cost the healthcare system?
  2. How many patients are eligible?
  3. Will insurance companies reimburse it?
  4. Can the government afford it?
  5. What price should be proposed?
* **Objective**: Build a tool that provides quick, approximate estimates within minutes.
* **Target Users**:
  * Market Access Team
  * Pricing Team
  * Health Economics / HEOR
  * Product Managers
  * Commercial Teams

---

## 2. Tool Inputs & Outputs

### Inputs
* **Drug Information**: Name, Price/Dosage, Treatment Duration
* **Disease Information**: Target Patient Population, Disease Incidence, Disease Prevalence
* **Market Information**: Country, Healthcare System, Reimbursement Rules
* **Eligibility**: Age, Gender, Disease Severity, Prior Interventions
* **Adoption**: Expected Market Share, Uptake Rate

### Outputs
* Estimated Eligible Patients
* Estimated Annual Drug Cost
* Total Budget Impact / Budget Cost
* Cost per Patient
* Best Pricing Scenario / Sensitivity Analysis

### Visualizations Required
* Graphs & Dashboards (Executive Dashboard, Cross-country heatmaps, Patient Funnel, Affordability Gauge)

---

## 3. Core Reading & Standards (ISPOR)
* **ISPOR**: International Society for Pharmacoeconomics and Outcomes Research
  * World's leading organization that develops standard guidelines for:
    1. Drug Pricing
    2. Market Access
    3. Budget Impact Analysis (BIA)
    4. Cost-Effectiveness Analysis (CEA)
    5. Health Technology Assessment (HTA)
    6. Real-World Evidence (RWE)
* **Key Literature**:
  1. *ISPOR Good Practice Task Force - Budget Impact Analysis: Principles of Good Practice*
  2. *Original ISPOR Budget Impact Guidelines*
  3. *ISPOR Economic Evaluation Guidelines*

---

## 4. Modern System Architecture & Tech Stack

### Data & ML Pipeline Architecture
1. **Inputs**: Drug Information, Patient Population, Disease Prevalence, Treatment Patterns, Drug Cost, Market Share, Country Reimbursement Rules.
2. **Feature Engineering**: XGBoost / LightGBM / CatBoost.
3. **ML Model**: XGBoost / LightGBM / CatBoost for Budget Impact Prediction & Time Series Forecasting / Monte Carlo Simulations in Health Economics.
4. **Explainability**: SHAP (XAI) for explaining predictions and feature importance.
5. **Dashboard & UI**: Streamlit (for rapid prototyping/interactive tool) or Next.js + React.
6. **Business Intelligence**: Power BI (for executive dashboards).
7. **Database**: PostgreSQL (with pgvector for RAG / Supabase).

### Tech Stack Choices
* **Language/Libraries**: Python, Pandas, NumPy, Scikit-Learn, XGBoost, LightGBM, CatBoost, SHAP, LangChain.
* **Frontend**: Streamlit / Next.js + Tailwind CSS + Recharts + TanStack Query.
* **Backend**: FastAPI (Async, Pydantic Validation).
* **Database / Vector Store**: PostgreSQL + `pgvector` via SQLAlchemy / Supabase.
* **Deployment & DevOps**: Docker, Vercel (Frontend), Render / Supabase (Backend/DB), Git, OpenTelemetry.

---

## 5. End-to-End Workflow & User Persona Mapping

### System Workflow
1. **User** inputs scenario variables via UI.
2. **Streamlit / Web App** handles input form and passes parameters.
3. **Python Engine** runs budget impact calculation algorithms and ML predictions.
4. **ML & SHAP** compute predictive estimates and explainability metrics.
5. **Database (PostgreSQL)** stores inputs, parameters, and calculated results.
6. **Power BI / Executive Dashboard** reads stored data from PostgreSQL and updates high-level executive dashboards automatically.
7. **AI Copilot / RAG** retrieves ISPOR/HTA guidelines to justify numbers.

### User Persona Split
* **Data Scientist / AI Engineer**: Uses Python, Streamlit, ML Models, ISPOR Budget Impact Engine, PostgreSQL.
* **Business Managers / Executives**: Use Power BI for executive summaries; do not need to interact with raw ML code.
* **AI Copilot Assistants (Layered on Top)**:
  1. *Market Access AI Assistant*
  2. *ISPOR Guideline Assistant*
  3. *HTA Assistant (NICE, CADTH, etc.)*
  4. *Drug Pricing Advisor*
  5. *Explain My Dashboard Bot*
  6. *Scenario Executive Summary Generator*

---

## 6. Standout Project Architecture & Top AI Features

### Standout Project Components
1. Interactive Streamlit / React Dashboard
2. ISPOR-Compliant Budget Impact Engine
3. ML Prediction (XGBoost / LightGBM / CatBoost)
4. SHAP Explainability Integration
5. PostgreSQL Database Integration
6. Power BI Executive Dashboards
7. AI Budget Copilot & Scenario Generator
8. RAG Chatbot for ISPOR, HTA, and Clinical Documents

### Top 3 AI Feature Picks
1. **Budget Impact Copilot**:
   * Explains predictions in plain natural language.
   * Answers "What-if" scenario questions.
   * Runs automated multi-variable scenario analysis.
2. **ISPOR & HTA Knowledge Assistant**:
   * Answers queries based on ISPOR guidelines and HTA documents.
   * Explains market access concepts with exact citations.
3. **Executive Report Generator**:
   * Summarizes complex health economic outputs into business-ready language.
   * Generates early-stage downloadable presentation/PDF reports.

---

## 7. Business Questions, Key Stakeholders & Hackathon Context

### Strategic Questions to Address
* **Business Problems**: Rapid estimation of financial impact, reimbursement feasibility, and optimal pricing strategy.
* **Target Audience**: Internal decision-making (early stage) vs. External submission (HTA bodies like NICE, CADTH, AMCP).
* **Initial Therapeutic Focus**: Obesity & Diabetes (Cardiometabolic).
* **Data Context**: Combining synthetic/public data with historical pricing and epidemiological sources.
* **Success Criteria**: High transparency, capability for multi-scenario adjustments (uptake rate, market share, treatment duration, eligible population), and seamless UX.

### Hackathon / Project Details
* **Key Contacts / Stakeholders**: Vamsi Preetham Singh (Director), Nithya Sunil Krishnan (Director), Gowtham, Supraja.
* **Timeline**: Sep-6 (Qualifier Round / Hackathon Finale).
* **Deliverables**: Frame Prototype, PoC, Concise Presentation, Project Report.
* **Judging Criteria**: Innovation, Tech Implementation, Business Impact, Feasibility, Presentation Quality.

### First Week's Deliverables
1. ISPOR Budget Impact Analysis Workflow definition.
2. Build core Budget Calculation Engine in Python.
3. Create Streamlit dashboard with core inputs/outputs.
4. Add scenario analysis capabilities.
5. Explore ML model integration (if historical data exists).

---

## 8. Market Intelligence: Obesity & GLP-1/GIP Landscape (2025–2026+)

### Key Players & Major Drugs
#### **Novo Nordisk**
* **Injectables**: 
  * Semaglutide: Wegovy (Obesity), Ozempic (Diabetes)
  * Saxenda (Liraglutide)
* **Oral Pills**: 
  * Oral Semaglutide (Rybelsus)
  * Wegovy Pills (Launching 2026)
* **Metrics**: 14% body weight reduction (Semaglutide); 2025 Revenue ~$44 Billion.
* **Pricing (2026)**: Wegovy ~$149/month up to $299/month.
* **M&A / Pipeline**: Attempted acquisition of Metsera (biotech with promising obesity candidates) to compete with Eli Lilly.

#### **Eli Lilly**
* **Injectables**: 
  * Tirzepatide (Dual GIP/GLP-1): Zepbound (Obesity), Mounjaro (Diabetes)
* **Next-Gen Pipeline**:
  * **Retatrutide**: Experimental "triple agonist" (GLP-1, GIP, Glucagon). Phase-3 trials showed **24.2% (up to 71.2 lbs)** weight loss—notably higher than Wegovy/Zepbound.
  * **Orforglipron** (Oral GLP-1).
* **Metrics**: ~20% weight reduction (Tirzepatide); 2025 Revenue ~$40 Billion.

#### **Emerging Competitors (2026–2031)**
* Expected launch of ~16 new obesity drugs over 5–6 years, competing for a GLP-1/Obesity market projected to reach **$200 Billion by 2031**.
* **Pfizer**: Oral GLP-1
* **Amgen**: MariTide (GLP-1/GIPR)
* **AstraZeneca / Eccogene**: In-licensed oral GLP-1
* **Roche / Carmot**: CT-388, Petrelintide
* **Structure Therapeutics**: Bleniglipron (Oral)
* **Terns Pharmaceuticals**: Oral GLP-1
* **Viking Therapeutics**: VK2735
* **Zealand Pharma**: Petrelintide

---

## 9. Data Structure & Database Design

### Target Diabetes & Obesity Drug Database Schemas
1. **Obesity Anchor Comparators**: Wegovy, Zepbound, Saxenda, Orforglipron.
2. **GLP-1 Diabetes Comparators**: Ozempic, Mounjaro, Rybelsus.
3. **Rapid-Acting Insulin**: NovoRapid / Novolog, Humalog, Apidra.
4. **Long-Acting Insulin**: Tresiba, Lantus, Toujeo, Basaglar.
5. **Insulin Biosimilars**: Semglee (Biocon/Viatris), Rezvoglar.

### Database Architecture (8 Core SQL Tables in Supabase/PostgreSQL)
* **Tables**: Drug_Master, Disease_Epidemiology, Country_Reimbursement_Rules, Historical_Pricing, Market_Share_Projections, Simulation_Results, RAG_Documents, User_Scenarios.

---

## 10. Industry Benchmarks & Existing Tools

### Internal & Industry Software Examples
* **Novo Nordisk Internal Platform**: **MEDIX** — Partnered with Accenture/Salesforce to build MEDIX, a proprietary Market Access CRM & data engine used by 2000+ sales and market access team members.
* **Industry Standard Vendors & Tools**:
  * **Certara**: HEOR Tools, BaseCase dashboarding.
  * **IQVIA**: Payer Analytics, Global Market Access evidence.
  * **Evidera (Thermo Fisher)**: HEOR & Market Access consulting/tools.
  * **ICON plc**: HEOR & Pricing analytics.
  * **TreeAge Software**: Decision tree and Markov modeling for health economics.
  * **CADTH / AMCP / CHERISH**: Standardized template budget impact tools (Excel/R-Shiny/TreeAge).

---

## 11. Full System Layered Architecture

```
+-----------------------------------------------------------------------+
| LAYER 1: FRONTEND & UI                                                |
| - Web App (Next.js / Streamlit)                                       |
| - Inputs: Indication, Country, Patient Segment, Price Assumptions     |
| - Outputs: Affordability Dashboard, Heatmaps, Patient Funnel          |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
| LAYER 2: BACKEND & DATABASE                                           |
| - FastAPI Engine                                                      |
| - PostgreSQL / Supabase DB (Countries, Drugs, Prices, Epidemiological) |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
| LAYER 3: ANALYTICS, ML & RAG                                          |
| - ISPOR Calculation Engine (Deterministic Financial Modeling)         |
| - ML Model (XGBoost/LightGBM/CatBoost) for Uptake/Impact Prediction  |
| - SHAP Engine for Model Explainability                                |
| - Vector DB + RAG Engine (ISPOR Guidelines, HTA Rationale, NICE Docs) |
| - LLM Narrative Engine (Generates Executive Summaries & Justifications)|
+-----------------------------------------------------------------------+
```

---

## Summary of Action Items & Next Steps
1. Finalize core ISPOR mathematical formulas for early-stage budget impact calculation.
2. Setup PostgreSQL database with baseline GLP-1/Insulin dataset.
3. Build FastAPI backend endpoints for scenario calculations.
4. Implement Streamlit UI for rapid iteration prior to finale.
5. Ingest ISPOR PDF guidelines into Vector DB for RAG Co-pilot integration.
