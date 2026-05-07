
# 🏨 Luxury Hotel Booking System

> A modern, full-stack hotel booking platform built for hackathons, placements, and real-world deployment. Fast, secure, and feature-rich.

---

## 🚀 Project Highlights
- **End-to-End Booking:** Search, filter, and book hotel rooms with real-time availability.
- **User Roles:** Separate flows for Admin and Customer, with secure authentication.
- **Smart Pricing:** Automatic calculation of nights, taxes, and total cost.
- **PDF Invoices:** Downloadable invoices for every booking.
- **Booking History:** View, manage, and cancel bookings.
- **Analytics:** Visualize booking trends with interactive charts.
- **Responsive UI:** Works seamlessly on desktop and mobile.

---

## 🛠️ Tech Stack
- **Backend:** Python, Flask, MySQL
- **Frontend:** HTML5, CSS3, JavaScript (ES6), Chart.js
- **PDF Generation:** ReportLab (Python)
- **Authentication:** Secure password hashing, session management

---

## 📸 Screenshots
<!--
Add screenshots here for demo (UI, booking flow, analytics, etc.)
Example:
![Login Page](frontend/screenshots/login.png)
![Room Search](frontend/screenshots/room_search.png)
-->

---

## 📁 Project Structure
```
hotel-booking/
│
├── backend/      # Flask API server and business logic
├── frontend/     # HTML, CSS, JS for the web interface
├── database/     # Database schema (MySQL)
└── README.md
```

---

## ⚡ Quick Start
1. **Clone the repository:**
   ```bash
   git clone https://github.com/nidhica/Hotel_Booking.git
   cd Hotel_Booking
   ```
2. **Install backend dependencies:**
   - Requires Python 3 and MySQL
   - Install Python packages:
     ```bash
     pip install -r requirements.txt
     ```
3. **Set up the database:**
   - Create a MySQL database and user
   - Run the SQL script in `database/schema.sql`
   - Configure your database credentials (see `backend/db.py`)
4. **Run the backend server:**
   ```bash
   cd backend
   python app.py
   ```
5. **Open the frontend:**
   - Open `frontend/index.html` in your browser

---

## 🧑‍💻 Demo Credentials
- **Admin:** `admin@hotel.com` / `admin123`
- **Customer:** `customer@hotel.com` / `customer123`

---

## 💡 Notes
- **Security:** Never commit real database credentials to the repository.
- **Setup:** Anyone cloning this repo must set up their own MySQL instance and credentials.
- **Customization:** Easily extendable for new features, payment integration, or deployment.

---

## 🤝 Contributing
Pull requests and suggestions are welcome! For major changes, please open an issue first to discuss what you would like to change.

---

## 📫 Contact
For queries, reach out via [GitHub Issues](https://github.com/nidhica/Hotel_Booking/issues) or email.
