# LebLibrary (ספריית לייבוביץ)

A personal digital library and article management platform, built to share knowledge, articles, and resources in a clean, accessible format. 

Live Site: [https://leblibrary.co.il](https://leblibrary.co.il)

## Overview
This project is a custom Django-based web application serving as a centralized repository for articles, tutorials, and books. It features a responsive reading interface, a dedicated book catalog, and integrated SEO tracking. The platform is designed with simplicity and a distraction-free user experience in mind.

## Key Features
* **Article & Content Management:** Browse and read structured articles with a built-in reading progress indicator.
* **Responsive UI:** Mobile-friendly layouts, clean navigation, and smooth modal interactions.
* **SEO Optimized:** Verified and integrated with Google Search Console for organic search visibility.
* **Static Asset Management:** Structured handling of static files, CSS, and custom branding (Favicon).

## Tech Stack
* **Backend:** Python, Django
* **Frontend:** HTML5, CSS3, JavaScript
* **Server & Deployment:** Ubuntu Linux, Gunicorn, Nginx
* **Version Control:** Git & GitHub

---

## Deployment & Maintenance Cheat Sheet
This section documents the standard workflow for updating the live production server.

### 1. Pushing Local Changes (Development Environment)
After modifying templates (e.g., `base.html`), adding static files, or updating Python logic:
```bash
# Stage all changes (use -f if forcing hidden files like staticfiles/)
git add .

# Commit with a descriptive message
git commit -m "Update description here"

# Push to the main branch
git push