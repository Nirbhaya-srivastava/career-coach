import sys
import logging
from mcp.server.fastmcp import FastMCP

# Create a FastMCP server
mcp = FastMCP("CareerCoachTools")

@mcp.tool()
def search_courses(skill: str) -> str:
    """Search for online courses to learn a specific skill.

    Args:
        skill: The skill to search courses for (e.g. 'Python', 'AWS', 'Docker').
    """
    courses = {
        "python": [
            "Introduction to Python Programming (Google / Coursera)",
            "Python for Data Science and Machine Learning (Udemy)",
            "Complete Python BootCamp (Udemy)"
        ],
        "aws": [
            "AWS Certified Cloud Practitioner (A Cloud Guru)",
            "Ultimate AWS Certified Developer Associate (Udemy)"
        ],
        "docker": [
            "Docker Technologies for DevOps and Developers (Udemy)",
            "Docker and Kubernetes: The Complete Guide (Udemy)"
        ],
        "react": [
            "React - The Complete Guide (Udemy)",
            "Modern React with Redux (Udemy)"
        ],
        "sql": [
            "The Complete SQL Bootcamp (Udemy)",
            "SQL for Data Analytics (Coursera)"
        ]
    }
    key = skill.lower().strip()
    found = []
    for k, v in courses.items():
        if k in key or key in k:
            found.extend(v)
    if not found:
        return f"No specific courses found for '{skill}'. We recommend searching on Coursera or edX for introductory to advanced material."
    return "Here are recommended courses:\n" + "\n".join(f"- {c}" for c in found)

@mcp.tool()
def get_project_ideas(role: str) -> str:
    """Retrieve sample portfolio project ideas for a given career role.

    Args:
        role: The target role (e.g. 'Frontend Developer', 'Data Scientist', 'Backend Engineer').
    """
    ideas = {
        "frontend": [
            "Project 1: Personal Portfolio Website. Tech: React, Tailwind CSS. Build a responsive, highly accessible portfolio to showcase projects.",
            "Project 2: E-commerce Product Catalog. Tech: Next.js, Stripe. Implement client-side filtering, cart functionality, and checkout integration."
        ],
        "data scientist": [
            "Project 1: Customer Churn Predictor. Tech: Pandas, Scikit-learn, FastAPI. Clean a churn dataset, build a Random Forest classifier, and serve it via an API.",
            "Project 2: Text Summarization Tool. Tech: Hugging Face Transformers, Streamlit. Fine-tune a BART model to summarize articles and create a simple web app."
        ],
        "backend": [
            "Project 1: Task Management API. Tech: FastAPI, PostgreSQL, Docker. Build a RESTful API with JWT auth, database migrations, and containerized dev environments."
        ]
    }
    role_key = role.lower().strip()
    found = []
    for k, v in ideas.items():
        if k in role_key or role_key in k:
            found.extend(v)
    if not found:
        return f"No pre-defined portfolio projects for '{role}'. We recommend building a full-stack CRUD application or an API that integrates with a public dataset (e.g., weather, stocks) using your target tech stack."
    return "Here are recommended portfolio projects:\n" + "\n".join(f"- {v}" for v in found)

@mcp.tool()
def fetch_job_skills(job_title: str) -> str:
    """Fetch the essential skills required for a given job title.

    Args:
        job_title: The name of the job title (e.g. 'Backend Engineer', 'Frontend Engineer', 'Data Scientist').
    """
    skills_map = {
        "backend": "Required Skills: Python/Go/Java, Databases (SQL/NoSQL), REST APIs, Docker, System Design, Git.",
        "frontend": "Required Skills: JavaScript/TypeScript, React/Vue, HTML5/CSS3, Responsive Design, State Management (Redux/Zustand), Web Performance.",
        "data scientist": "Required Skills: Python, SQL, Statistics, Machine Learning (Scikit-learn, PyTorch), Data Visualization (Tableau/Matplotlib), Pandas.",
        "product manager": "Required Skills: Product Strategy, Agile/Scrum, User Research, Data Analytics, Roadmapping, Cross-functional Communication."
    }
    title_key = job_title.lower().strip()
    found = []
    for k, v in skills_map.items():
        if k in title_key or title_key in k:
            found.append(v)
    if not found:
        return f"For '{job_title}', key skills typically include: Professional Communication, Project Management, and specialized tools/technologies in that domain."
    return "\n".join(found)

if __name__ == "__main__":
    mcp.run()
