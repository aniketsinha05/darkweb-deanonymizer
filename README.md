# darkweb-deanonymizer

> Official prototype for **Smart India Hackathon 2026** (Problem Statement: **SIH26151**).
> An AI-driven cybersecurity forensics tool designed to map, track, and de-anonymize dark web threat actors across multiple aliases using **stylometry**, **metadata analysis**, and **graph network intelligence**.

---

## 1. Problem Summary

Threat actors on dark web forums and marketplaces rarely use a single identity. They create new handles after bans, exit scams, or operational-security scares. Investigators therefore face an **alias-linking problem**: given thousands of pseudonymous accounts, which ones are probably operated by the same person or group?

This project builds an analyst-facing system that:

1. Ingests lawfully obtained or public/synthetic dark web text and metadata.
2. Produces a ranked list of **probable alias links** with confidence scores.
3. Visualizes relationships as an interactive **entity graph**.
4. Explains *why* two aliases were linked, so evidence is auditable by a human analyst.

> **Scope note:** The tool outputs *probabilistic attribution leads* for investigators. It does not output "proof" of identity, and every link must be reviewed by a human analyst.

---

## 2. Approach Overview

The solution is a multi-signal pipeline. No single signal is reliable on its own, so we fuse three independent evidence streams and let a graph layer reconcile them.

```
 ┌────────────┐   ┌──────────────┐   ┌────────────────────┐   ┌───────────────┐
 │ Data       │ → │ Feature      │ → │ Alias Similarity   │ → │ Graph         │
 │ Ingestion  │   │ Extraction   │   │ Scoring (Fusion)   │   │ Intelligence  │
 └────────────┘   │ - Stylometry │   └────────────────────┘   └──────┬────────┘
                  │ - Metadata   │                                    │
                  │ - Behavior   │                            ┌───────▼────────┐
                  └──────────────┘                            │ Analyst        │
                                                              │ Dashboard + XAI│
                                                              └────────────────┘
```

---

## 3. Step-by-Step Approach

### Phase 1: Data Collection & Preparation

- **Use only legal, ethical sources.** Public research datasets, synthetic/simulated forum data, and any data explicitly provided by the hackathon organizers or authorized agencies.
- Candidate sources to explore: academic dark web corpora, leaked-forum datasets released for research, and synthetic data generated with LLMs to mimic multi-alias actors (useful because ground truth is known).
- **Schema** (normalized): `post_id, alias, platform, thread_id, timestamp, text, language, links, attachments, PGP keys, crypto addresses, contact handles`.
- **Cleaning:** remove quoted replies, signatures, boilerplate, and URLs from text before stylometry so models learn the author, not the template.
- **Ground truth:** build a labeled set of known same-author alias pairs (from synthetic data or published research) for training and evaluation.

### Phase 2: Stylometric Analysis (Who writes alike?)

Capture the writing "fingerprint" of each alias.

| Feature family | Examples |
|---|---|
| Lexical | Word/char n-grams, vocabulary richness, function-word frequencies, slang/leetspeak habits |
| Syntactic | POS-tag n-grams, sentence length distribution, punctuation habits |
| Structural | Capitalization, emoji use, paragraph/line-break style, greeting and sign-off patterns |
| Language/Code-mixing | Hinglish and multilingual patterns, transliteration quirks, typo patterns |
| Neural | Transformer embeddings (e.g., fine-tuned BERT/XLM-R) trained with a **contrastive/Siamese objective** so same-author posts sit close in vector space |

**Method:** Start with a classical baseline (TF-IDF char n-grams + cosine similarity / SVM), then improve with a Siamese transformer. Compare both and report the gain.

### Phase 3: Metadata & Behavioral Analysis (When and how do they act?)

- **Temporal patterns:** posting hours, activity heatmaps, inferred time zone, active-day rhythms.
- **Platform behavior:** forums frequented, product categories, thread-reply patterns, response latency.
- **Technical artifacts (when present in the data):** reused PGP keys, crypto wallet addresses, contact handles (Telegram/Jabber/email), shared file hashes, image EXIF fragments in the dataset.
- **Cross-reference hard identifiers** (same wallet, same PGP key) as *high-confidence* links; treat soft signals (posting time) as *supporting* evidence.

### Phase 4: Alias Similarity Scoring (Fusion)

- For each alias pair, compute a vector of similarity scores: `[stylometry, temporal, platform overlap, shared identifiers, topic similarity]`.
- Train a **gradient-boosted classifier (XGBoost/LightGBM)** or a small neural fusion head to output `P(same actor)`.
- Use **blocking / approximate nearest neighbors (FAISS)** to avoid comparing every pair at scale.
- **Calibrate** probabilities (Platt scaling / isotonic regression) so a "0.85" actually means roughly 85% likely.

### Phase 5: Graph Network Intelligence (Who connects to whom?)

- Build a graph where **nodes** = aliases, wallets, keys, forums, and threads; **edges** = interactions, shared identifiers, and model-predicted similarity.
- Apply **community detection** (Louvain/Leiden) to cluster aliases into candidate "actor identities".
- Use **centrality metrics** and link prediction (node2vec / GNN such as GraphSAGE) to surface key actors and likely missing links.
- Store in **Neo4j** (or NetworkX for the prototype) for fast analyst querying.

### Phase 6: Explainability & Analyst Dashboard

- **Why-linked panel:** top contributing features per link (SHAP values, most similar phrases, shared identifiers).
- **Interactive graph view:** filter by confidence, platform, and time range.
- **Timeline view:** when each alias appeared or went dormant, to spot "alias handover" patterns.
- **Case export:** generate a PDF/JSON report with evidence trail for investigators.

### Phase 7: Evaluation

- **Metrics:** precision, recall, F1 for alias-pair linking; ROC-AUC; top-k accuracy for "find other aliases of X"; clustering purity for actor groups.
- **Baselines:** stylometry-only vs. metadata-only vs. fused model, to demonstrate that fusion helps.
- **Robustness tests:** adversarial stylometry (an author deliberately disguising their style), short-text posts, and multilingual content.
- **Error analysis:** document false positives, since wrongly linking innocent users is the main risk.

---

## 4. Proposed Tech Stack

| Layer | Tools |
|---|---|
| Language | Python 3.11+ |
| NLP / ML | scikit-learn, spaCy, Hugging Face Transformers, PyTorch, sentence-transformers |
| Fusion models | XGBoost / LightGBM, SHAP |
| Similarity search | FAISS |
| Graph | NetworkX → Neo4j, PyTorch Geometric |
| Backend | FastAPI |
| Frontend | React + D3.js / Cytoscape.js / Streamlit (for a fast prototype) |
| Storage | PostgreSQL + Elasticsearch (text search) |
| Deployment | Docker, docker-compose |

---

## 5. Suggested Repository Structure

```
darkweb-deanonymizer/
├── data/                 # synthetic / public datasets (no raw sensitive data committed)
├── notebooks/            # exploration and experiments
├── src/
│   ├── ingestion/        # parsers and normalizers
│   ├── features/
│   │   ├── stylometry.py
│   │   ├── metadata.py
│   │   └── behavior.py
│   ├── models/           # siamese encoder, fusion classifier
│   ├── graph/            # graph construction, community detection
│   ├── explain/          # SHAP, evidence generation
│   └── api/              # FastAPI app
├── dashboard/            # frontend
├── tests/
├── docs/
└── README.md
```

---

## 6. Milestones / Timeline

| Stage | Goal |
|---|---|
| Week 1 | Finalize problem scope, gather/generate datasets, define schema |
| Week 2 | Stylometry baseline + evaluation harness |
| Week 3 | Metadata/behavioral features + fusion model |
| Week 4 | Graph construction, community detection, link prediction |
| Week 5 | Dashboard, explainability, report export |
| Week 6 | Evaluation, robustness tests, documentation, demo video, final pitch |

---

## 7. Ethics, Legal & Responsible-Use Considerations

De-anonymization tools carry real risk of harm if misused or wrong. This project commits to:

- **Lawful use only:** designed for authorized law-enforcement and cybersecurity-research contexts, in compliance with Indian law (including the IT Act, 2000 and the Digital Personal Data Protection Act, 2023).
- **Human in the loop:** outputs are investigative leads, never automated accusations.
- **Data minimization:** work with public, synthetic, or officially provided data; do not store or redistribute sensitive personal data in this repository.
- **Transparency:** every link is accompanied by an explanation and a confidence score.
- **Bias & error auditing:** report false-positive rates and test across languages and writing styles.
- **Access control & audit logs** in any deployed version.

---

## 8. Expected Outcomes

- A working prototype that links aliases with measurable accuracy on benchmark/synthetic data.
- An interactive graph dashboard with explainable evidence per link.
- An evaluation report comparing individual signals against the fused approach.
- A documented, ethical framework for deployment by investigators.

---

## 9. Future Scope

- Real-time ingestion pipeline and alerting for new alias activity.
- Cross-lingual stylometry for Indian regional languages and code-mixed text.
- Image and file-hash correlation across marketplaces.
- Federated deployment so agencies can collaborate without sharing raw data.
- Defenses against adversarial style obfuscation and LLM-generated text.

---

## 10. Getting Started *(to be updated)*

```bash
git clone https://github.com/aniketsinha05/darkweb-deanonymizer.git
cd darkweb-deanonymizer
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

---

## 11. Team

Hitakshi Bhanushali
Aniket Sinha

## 12. License

*Add a license (e.g., MIT) after confirming SIH submission guidelines.*