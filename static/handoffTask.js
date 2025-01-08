function handoffTask(taskId, mode) {
  fetch("/handoff_task", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ task_id: taskId, mode: mode })
  })
  .then(response => response.json())
  .then(data => {
    if (data.status) {
      alert("Handoff result: " + data.status);
      // Maybe location.reload() or update the UI
    } else {
      alert("Handoff error: " + data.error || "Unknown");
    }
  })
  .catch(err => console.error(err));
}
