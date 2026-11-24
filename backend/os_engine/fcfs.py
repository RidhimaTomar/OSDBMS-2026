MEETING_MINUTES = 60  

def fcfs(burst_time):
    waiting = []
    turnaround = []
    current = 0

    for burst in burst_time:
        waiting.append(current)
        current += burst
        turnaround.append(current)

    return {
        "waiting_time": waiting,
        "turnaround_time": turnaround,
        "average_waiting_time": sum(waiting) / len(waiting) if waiting else 0,
        "average_turnaround_time": sum(turnaround) / len(turnaround) if turnaround else 0
    }


def fcfs_order(requests):
    return sorted(requests, key=lambda r: (r.get("requested_at") or "", r["appointment_id"]))


def fcfs_queue(requests):

    ordered = fcfs_order(requests)
    if not ordered:
        return {}

    result = fcfs([MEETING_MINUTES] * len(ordered))
    size = len(ordered)

    return {
        r["appointment_id"]: {
            "position": i + 1,
            "size": size,
            "ahead": i,
            "wait_minutes": result["waiting_time"][i],
            "turnaround_minutes": result["turnaround_time"][i],
        }
        for i, r in enumerate(ordered)
    }
