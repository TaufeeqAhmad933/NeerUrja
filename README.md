# NeerUrja
### Run the building when the sun is up.

NeerUrja is a solar-aware water pumping scheduler for buildings with rooftop solar. It compares different pumping schedules to understand how solar generation, electricity costs and water requirements affect daily operations.

The idea is simple: instead of running a water pump only at fixed times, can we choose a better schedule based on when solar energy is available, while still maintaining sufficient water?

**Live Demo:** https://main.d189w7c14irqkc.amplifyapp.com/

## The Problem

Buildings with rooftop solar can still rely on grid electricity for water pumping when their schedules don't align with solar generation. Fixed schedules may also ignore changing water demand, electricity tariffs and tank levels.

NeerUrja explores whether smarter scheduling can reduce modeled electricity costs without compromising water requirements.

## What NeerUrja Does

- Compares three strategies: Habit, Timer and Optimizer.
- Supports clear-sky and monsoon/overcast scenarios.
- Simulates a full day using 96 intervals of 15 minutes each.
- Tracks solar generation, grid imports, electricity costs and pump runtime.
- Visualizes water tank levels and operational constraints.
- Provides an interactive dashboard for comparing results.

## How It Works

**Habit:** Uses the baseline pumping schedule as a reference.

**Timer:** Runs the pump during a fixed time window, subject to operational safeguards.

**Optimizer:** Uses deterministic dynamic programming to select a pumping schedule based on forecast electricity costs and operating constraints.

Each strategy is evaluated against the same simulated conditions. The simulator calculates grid consumption, solar usage, operating costs and tank levels.

A strategy is not selected based on cost alone. It must also satisfy the project's water and operational constraints, including the end-of-day tank level requirement.

## Sample Results

The following results are from the clear-sky demo scenario.

| Metric | Habit | Timer | Optimizer |
|---|---:|---:|---:|
| Operating cost | ₹1,179.81 | ₹1,099.81 | ₹1,122.55 |
| Grid import | 147.5 kWh | 137.5 kWh | 140.3 kWh |
| Solar self-consumption | 55.2% | 57.8% | 57.7% |
| Pump energy | 10 kWh | 7.5 kWh | 10 kWh |
| Constraint violations | 0 | 0 | 0 |
| Meets end-of-day sustainability check | Yes | No | Yes |

Although Timer has the lowest raw cost, it finishes with less water than it started with. Under our eligibility rules, it does not qualify as the best strategy.

The Optimizer is the lowest-cost eligible strategy in this scenario. Its modeled operating cost is ₹57.26 lower than Habit, a difference of approximately 4.85%.

These are simulation results, not measured savings from a real building.

## Tech Stack

**Frontend**
- React
- Vite
- TypeScript

**Backend**
- Python
- FastAPI
- Pydantic
- Dynamic programming and simulation logic

**AWS**
- AWS Amplify for frontend hosting
- Amazon API Gateway for API endpoints
- AWS Lambda for backend execution
- Amazon S3 for demo scenario storage
- Amazon CloudWatch for logs and monitoring
- AWS SAM for infrastructure deployment

## Architecture

```text
React + Vite Frontend
        |
        v
AWS Amplify
        |
        v
Amazon API Gateway
        |
        v
AWS Lambda
        |
        +---- Amazon S3
        |     Scenario data
        |
        +---- Scheduling and optimization
        |
        +---- Simulation and metrics
        |
        v
Results returned to the dashboard

Amazon CloudWatch: Logs and monitoring
AWS SAM: Infrastructure deployment
```

The frontend sends requests to the backend to load a scenario and run the comparison. The backend evaluates the three strategies and returns the results for the dashboard to display.

## Running Locally

You'll need Node.js and Python installed.

### 1. Clone the repository

```bash
git clone https://github.com/TaufeeqAhmad933/NeerUrja.git
cd NeerUrja
```

### 2. Start the backend

```bash
cd neerurja-backend
python -m venv .venv
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install the dependencies listed in the backend's dependency file, then start the FastAPI application using the module and application path defined in the project.

### 3. Start the frontend

Open another terminal:

```bash
cd frontend
npm ci
```

Set `VITE_API_BASE_URL` in your local `.env` file to your backend URL, then run:

```bash
npm run dev
```

Open the local URL printed by Vite.

Check the backend dependency file and application entry point for the exact installation and startup commands for your checkout.

## Current Limitations

NeerUrja is a simulation-based prototype.

- Solar generation, building load and water demand come from demo scenario data.
- The application does not directly control a physical pump.
- The reported savings have not been validated using real building measurements.
- A real deployment would need live tank-level and energy data, reliable telemetry and independent pump safety controls.

The next step is to test the scheduling approach with real building data before integrating physical pump controls.

## Team

**hyderaBADDIEE**

- Taufeeq Ahmad
- Subbarayudu Bolisetty
- Manaswini Koratagiri

## Built for

WeMakeDevs × AWS Environmental Hacks
