# OSDBMS-V-2026-T068

## Project Overview

Unified Academic Scheduling and Management is a web-based campus management system developed using Python, SQLite, HTML, CSS, and JavaScript. It provides academic scheduling, faculty appointment booking, notifications, communication, and document-sharing features while demonstrating core Operating Systems and DBMS concepts.

## Features

- **Role-Based Authentication:** Separate access for administrators, faculty, and students.
- **Timetable Management:** Manage class schedules and detect faculty and classroom conflicts.
- **Appointment Booking:** Request, approve, cancel, and reschedule faculty appointments.
- **Venue Management:** Associate meeting venues with appointments.
- **Notifications:** Generate and manage appointment-related notifications.
- **Calendar:** View academic schedules and appointments.
- **Document Sharing:** Support document upload and download.
- **Student–Faculty Chat:** Facilitate academic communication.
- **OS Algorithm Simulations:** Demonstrate CPU scheduling, synchronization, deadlock detection, page replacement, and disk scheduling.

## Technologies Used

- Frontend: HTML, CSS, JavaScript
- Backend: Python
- Database: SQLite
- Communication: HTTP and JSON
- Concurrency: Python threading and locks

## Operating Systems Concepts

- CPU Scheduling: FCFS, Priority Scheduling, Round Robin
- Process Synchronization: Locks, mutual exclusion, critical sections, race conditions
- Deadlock Detection
- File I/O and resource management

## DBMS Concepts

- Relational database design
- SQL CRUD operations
- Primary and foreign keys
- Unique and NOT NULL constraints
- Joins, indexes, views, and triggers
- Transactions and rollback
- Referential integrity and parameterized queries

## Database Tables

The core database initialization script declares five tables:

1. `users` — Stores user accounts and roles.
2. `timetable` — Stores faculty schedules, subjects, time slots, and rooms.
3. `appointments` — Stores faculty appointment requests and their statuses.
4. `reschedule_requests` — Stores proposed appointment changes.
5. `notifications` — Stores user notifications and read status


## Conclusion

Our project integrates practical campus-management functionality with OS algorithm simulations and relational database operations. It demonstrates synchronization, resource allocation, scheduling, data integrity, and transaction management in a single project.

## Repository

[GitHub — OSDBMS-2026](https://github.com/RidhimaTomar/OSDBMS-2026)
