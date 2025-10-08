# MayWin - Nurse Scheduling Optimization System

An AI-driven nurse scheduling optimization project designed to improve fairness, efficiency, and staff satisfaction in healthcare facilities through intelligent shift assignment.

## 📋 Project Overview

MayWin addresses the critical challenge of nurse scheduling in Thai healthcare systems by automating shift assignments while balancing workload fairness, legal rest requirements, and individual preferences. The system aims to reduce nurse burnout, improve job satisfaction, and enhance overall hospital operational efficiency.

## 👥 Team

- **Chirayu Sukhum (Tuey)** - Backend & Optimization Lead
- **Thanakrit Punyasuntontamrong (Pass)** - Requirements & Documentation Lead
- **Kris Luangpenthong (Ken)** - Web Dashboard & QA Lead
- **Saran Watcharachokkasem (Ryuki)** - LINE Chatbot Lead
- **Jaiboon Limpkittisin (Boon)** - Mobile Application Lead

**Advisor:** Dr. Akkarit Sangpetch

## 🎯 Key Features

- **Optimization Engine**: Goal Programming-based scheduling that balances hard constraints (staffing rules, rest requirements) and soft constraints (preferences, fairness)
- **Multi-Platform Access**:
  - 📱 Mobile application for nurses to view and manage schedules
  - 🖥️ Web dashboard for hospital administrators
  - 💬 LINE chatbot for conversational preference submission
- **Human-in-the-Loop Design**: Administrators maintain control with parameter adjustments and schedule selection based on satisfaction metrics
- **Fairness-Focused**: Ensures equitable workload distribution and considers individual nurse preferences

## 🏗️ System Architecture

### Core Technologies

- **Backend**: Rust with Axum framework
- **Database**: PostgreSQL
- **Optimization**: Goal Programming with evaluation of:
  - Rust-based solvers (good_lp, coin_cbc)
  - Python-based solvers (Google OR-Tools, Gurobi Optimizer)
- **Conversational UI**: LINE Bot integration with NLU capabilities
- **Infrastructure**: CMKL APEX Supercomputer for large-scale optimization

### Key Components

1. **Natural Language Understanding (NLU)**: Converts chat-based preferences into structured data
2. **Optimization Engine**: Generates feasible schedules balancing constraints
3. **Decision Support System (DSS)**: Provides transparency and adaptability for administrators

## 🚀 Getting Started

> **Note:** Setup instructions will be added as the project develops

### Prerequisites

- Rust (latest stable version)
- PostgreSQL
- Python 3.x (for solver experimentation)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/maywin.git
cd maywin

# Backend setup
cd backend
cargo build

# Database setup
# (Instructions to be added)
```

## 📊 Project Status

**Current Phase:** Fall 2023 - Foundation & Prototyping

### Completed

- ✅ Domain understanding and stakeholder requirements gathering
- ✅ Literature review on nurse scheduling optimization
- ✅ Initial system requirements definition
- ✅ Project structure and collaboration tools setup

### In Progress

- 🔄 Optimization solver evaluation and selection
- 🔄 Proof-of-concept scheduling engine development
- 🔄 UI/UX wireframe design
- 🔄 Backend infrastructure setup

### Upcoming

- ⏳ Stakeholder feedback integration
- ⏳ Full system integration testing
- ⏳ Real-world validation with Bangkok Hospital

## 🎓 Research Foundation

This project builds upon academic research in nurse scheduling, particularly:

- Goal Programming approaches to multi-objective optimization
- Personnel scheduling literature
- Healthcare operations research

**Key reference:** Rerkjirattikal et al. (2020), "A Goal Programming Approach to Nurse Scheduling with Individual Preference Satisfaction"

## 📝 Project Deliverables

1. Fully functioning optimization engine
2. Mobile application for nurses
3. Web dashboard for hospital management
4. LINE chatbot for preference submission
5. Comprehensive documentation and evaluation reports

## 🤝 Stakeholders & Beneficiaries

**Primary Beneficiaries:**

- Nurses (improved work-life balance, preference satisfaction)
- Hospital management (efficient operations, reduced turnover costs)

**Secondary Beneficiaries:**

- Patients (better care quality)
- Doctors (improved support from nursing staff)

## 📈 Success Metrics

- Workload balance across nursing staff
- Preference satisfaction rates
- Computational efficiency
- Staff satisfaction scores
- Reduction in manual scheduling time

## ⚠️ Known Challenges

- Limited access to real hospital data due to privacy policies
- Complex fairness modeling requirements
- Variability in scheduling needs across different departments
- Gurobi academic license acquisition for CMKL

## 📄 License

*To be determined*

## 📧 Contact

For inquiries about this project, please contact the team through Dr. Akkarit Sangpetch at CMKL University.

---

**Last Updated:** October 8, 2025  
**Project Duration:** Fall 2023 - Spring 2024