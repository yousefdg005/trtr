# 🩺 MedLink - Home Care Dispatch Platform

MedLink is a comprehensive web platform designed to bridge the gap between patients in Libya (specifically Tripoli) and home healthcare providers. It enables patients to easily request home nurses, first-aid responders, and physiotherapists based on proximity and real-time availability, while providing medical professionals with a seamless way to find freelance opportunities.

## 🚀 Key Features

### 🧑‍⚕️ For Patients (Patient Portal)
- **Proximity-Based Matching:** Find the nearest available nurses within Tripoli's supported zones.
- **Interactive Location Selection:** Precisely select your location on an interactive map.
- **Real-Time Tracking:** Watch as your request is broadcasted and instantly notified when a nurse accepts.
- **Budget Control:** Set a minimum and maximum budget for the required medical service.

### 💼 For Medical Providers (Nurse Portal)
- **Job Discovery:** Receive nearby patient requests in real-time when toggled "Online".
- **Location Broadcasting:** Share your current location to receive proximity-based jobs (within a 10km radius).
- **Active Task Tracking:** View the current patient's location on an interactive map.
- **Debt & Balance System:** A wallet system tracks commissions; providers cannot accept new requests if their debt reaches 50 LYD until a top-up (Madar Card) is processed.

### 🛡️ For Administrators (Admin Dashboard)
- **System Control:** Turn the entire system online or offline via a master switch.
- **User Verification:** Review and approve pending nurse registrations, including viewing their medical licenses.
- **Financial Management:** Review submitted Madar recharge cards, approve payments, and manage nurse debt limits.

---

## 🏗️ System Architecture

![MedLink System Architecture](14854.png)

The MedLink platform utilizes a decoupled, three-tier architecture where three distinct user groups interact with their respective interfaces, all routed through a centralized persistence layer.

### 1. User Interfaces (The Portals)
- **Patient Service (`patient_app.py`):** Patients use this app to check system availability, create and track requests, and cancel them if needed. 
- **Administration (`admin_app.py`):** Administrators manage the entire service here. They set system availability, view active/pending requests, review nurse applications, and process payments.
- **Nurse Operations (`nurse_app.py`):** Nurses use this portal to register/log in, find nearby work, accept or cancel tasks, and submit payments.

### 2. Persistence Layer (`database.py`)
This central module acts as the backbone of the system, handling all database transactions and separating concerns into four main categories:
- **System Availability:** Reads/writes the global on/off switch for the platform.
- **Request Operations:** Manages the lifecycle of patient requests (creation, matching via spatial queries, tracking, cancellation).
- **Nurse Membership:** Handles nurse registration, authentication, and approval status.
- **Payment and Debt:** Manages the commission logic, debt threshold blocks, and payment reviews.

### 3. Database
- **PostgreSQL:** The core database securely storing all relational data, utilizing spatial features (PostGIS) for distance calculations between patients and nurses.

---

## 🛠️ Tech Stack

- **Backend Framework:** Streamlit (Python)
- **Database:** PostgreSQL (using psycopg2 and PostGIS for spatial queries)
- **Mapping & Location:** Folium & Streamlit-Folium
- **Styling:** Custom CSS (RTL support, Medical Theme, Responsive Design)

---

## ⚙️ Installation & Local Setup

### 1. Clone the repository
```bash
git clone https://github.com/yousefdg005/trtr.git
cd trtr
```

### 2. Create and activate a Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Database Setup
Ensure you have a **PostgreSQL** database with the **PostGIS** extension enabled. Configure your `.streamlit/secrets.toml`:
```toml
[database]
url = "postgresql://user:password@host:port/dbname"
```

### 5. Run the Applications
Run each portal separately:
```bash
streamlit run patient_app.py   # Patient Portal
streamlit run nurse_app.py     # Nurse Portal
streamlit run admin_app.py     # Admin Dashboard
```

---

## 📄 License
© 2026 Yousef Noureddine Elmgamez. All Rights Reserved.
