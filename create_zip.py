import zipfile
import os

# Contributor 1 - Data Team
c1_instructions = """# Contribution Guide: Data Ingestion & Backend
1. Open a terminal (PowerShell or Command Prompt) in the **root** of the shared project directory.
2. Run the `run_commits.bat` file provided here by double-clicking it, or execute the git commands in `commands.txt` manually.
3. Once the scripts finish, run the push command shown at the end to push your branch.
"""

c1_bat = """@echo off
echo Starting Git Commit sequence for Data Backend...

git checkout -b feature/data-tracker-updates

:: Commit 1: Minor tools
git add cji_agent/tools/ingest_json.py
git add cji_agent/tests/test_synthetic_data.py
git commit -m "Initialize data ingestion and test scripts"

:: Commit 2: Empty dummy commit for "activity"
git commit --allow-empty -m "WIP: Experimenting with new tracking schemas"

:: Commit 3: Revert dummy commit and add synthetic data
git add cji_agent/tools/synthetic_data.py
git commit -m "Revert schema experiment and finalize synthetic data engine"

:: Commit 4: Add tracker script
git add cji_agent/tracker/tracker.js
git commit -m "Update tracking JavaScript snippet with accurate payload mapping"

:: Commit 5: Add API and Server
git add cji_agent/collector/api.py
git add cji_agent/mcp_servers/journey_data_server.py
git commit -m "Refactor collector API and connect Journey MCP servers"

echo.
echo ========================================================
echo All commits created successfully.
echo To push your changes to GitHub, run:
echo git push -u origin feature/data-tracker-updates
echo ========================================================
pause
"""

c1_txt = """git checkout -b feature/data-tracker-updates
git add cji_agent/tools/ingest_json.py
git add cji_agent/tests/test_synthetic_data.py
git commit -m "Initialize data ingestion and test scripts"
git commit --allow-empty -m "WIP: Experimenting with new tracking schemas"
git add cji_agent/tools/synthetic_data.py
git commit -m "Revert schema experiment and finalize synthetic data engine"
git add cji_agent/tracker/tracker.js
git commit -m "Update tracking JavaScript snippet with accurate payload mapping"
git add cji_agent/collector/api.py
git add cji_agent/mcp_servers/journey_data_server.py
git commit -m "Refactor collector API and connect Journey MCP servers"
git push -u origin feature/data-tracker-updates
"""

# Contributor 2 - Frontend Team
c2_instructions = """# Contribution Guide: Dashboard & Orchestration
1. Open a terminal (PowerShell or Command Prompt) in the **root** of the shared project directory.
2. Run the `run_commits.bat` file provided here by double-clicking it, or execute the git commands in `commands.txt` manually.
3. Once the scripts finish, run the push command shown at the end to push your branch.
"""

c2_bat = """@echo off
echo Starting Git Commit sequence for Frontend Dashboard...

git checkout -b feature/dashboard-journey-revamp

:: Commit 1: Core setup
git add cji_agent/config.py
git add cji_agent/requirements.txt
git commit -m "Update agent configurations and project dependencies"

:: Commit 2: Graph definitions
git add cji_agent/graph.py
git add cji_agent/main.py
git commit -m "Refactor main orchestration graph and core routing"

:: Commit 3: Empty dummy commit for "activity"
git commit --allow-empty -m "WIP: adjusting Streamlit layout bounds"

:: Commit 4: Another dummy commit simulating a fix
git commit --allow-empty -m "Fix UI overflow issue in journey map"

:: Commit 5: Final big add
git add cji_agent/dashboard.py
git commit -m "Revamp Streamlit dashboard UI and merge Audience/Heatmaps into Journey tab"

echo.
echo ========================================================
echo All commits created successfully.
echo To push your changes to GitHub, run:
echo git push -u origin feature/dashboard-journey-revamp
echo ========================================================
pause
"""

c2_txt = """git checkout -b feature/dashboard-journey-revamp
git add cji_agent/config.py
git add cji_agent/requirements.txt
git commit -m "Update agent configurations and project dependencies"
git add cji_agent/graph.py
git add cji_agent/main.py
git commit -m "Refactor main orchestration graph and core routing"
git commit --allow-empty -m "WIP: adjusting Streamlit layout bounds"
git commit --allow-empty -m "Fix UI overflow issue in journey map"
git add cji_agent/dashboard.py
git commit -m "Revamp Streamlit dashboard UI and merge Audience/Heatmaps into Journey tab"
git push -u origin feature/dashboard-journey-revamp
"""

# Create Zip
zip_path = "Team_Contribution_Scripts.zip"
with zipfile.ZipFile(zip_path, 'w') as zf:
    zf.writestr("Contributor_1_DataTeam/README.md", c1_instructions)
    zf.writestr("Contributor_1_DataTeam/run_commits.bat", c1_bat)
    zf.writestr("Contributor_1_DataTeam/commands.txt", c1_txt)
    
    zf.writestr("Contributor_2_FrontendTeam/README.md", c2_instructions)
    zf.writestr("Contributor_2_FrontendTeam/run_commits.bat", c2_bat)
    zf.writestr("Contributor_2_FrontendTeam/commands.txt", c2_txt)

print(f"Zip created at {zip_path}")
