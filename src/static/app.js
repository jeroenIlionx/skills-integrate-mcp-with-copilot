document.addEventListener("DOMContentLoaded", () => {
  const activitiesList = document.getElementById("activities-list");
  const activitySelect = document.getElementById("activity");
  const signupForm = document.getElementById("signup-form");
  const loginForm = document.getElementById("login-form");
  const registerForm = document.getElementById("register-form");
  const logoutButton = document.getElementById("logout-button");
  const signupContainer = document.getElementById("signup-container");
  const authStatus = document.getElementById("auth-status");
  const signedInAs = document.getElementById("signed-in-as");
  const messageDiv = document.getElementById("message");
  let currentUser = null;

  function showMessage(message, status) {
    messageDiv.textContent = message;
    messageDiv.className = status;
    messageDiv.classList.remove("hidden");
  }

  function showLoggedOut() {
    currentUser = null;
    loginForm.classList.remove("hidden");
    registerForm.classList.remove("hidden");
    logoutButton.classList.add("hidden");
    signupContainer.classList.add("hidden");
    authStatus.textContent =
      "Sign in or create a student account to manage your registrations.";
  }

  async function updateAuthState() {
    const response = await fetch("/auth/me");
    if (response.status === 401) {
      showLoggedOut();
      return;
    }
    if (!response.ok) {
      throw new Error("Could not check the signed-in account");
    }

    const user = await response.json();
    currentUser = user;
    loginForm.classList.add("hidden");
    registerForm.classList.add("hidden");
    logoutButton.classList.remove("hidden");
    authStatus.textContent = `Signed in as ${user.email} (${user.role}).`;
    if (user.role === "student") {
      signedInAs.textContent = `Registering as ${user.email}`;
      signupContainer.classList.remove("hidden");
    } else {
      signupContainer.classList.add("hidden");
    }
  }

  async function fetchActivities() {
    try {
      const response = await fetch("/activities");
      if (!response.ok) {
        throw new Error("Could not load activities");
      }
      const activities = await response.json();
      activitiesList.replaceChildren();
      activitySelect.replaceChildren(new Option("-- Select an activity --", ""));
      Object.entries(activities).forEach(([name, details]) => {
        const activityCard = document.createElement("div");
        activityCard.className = "activity-card";
        const heading = document.createElement("h4");
        heading.textContent = name;
        activityCard.appendChild(heading);
        const description = document.createElement("p");
        description.textContent = details.description;
        activityCard.appendChild(description);
        const schedule = document.createElement("p");
        schedule.textContent = `Schedule: ${details.schedule}`;
        activityCard.appendChild(schedule);
        const availability = document.createElement("p");
        availability.textContent = `Availability: ${
          details.max_participants - details.participants.length
        } spots left`;
        activityCard.appendChild(availability);

        const participants = document.createElement("div");
        participants.className = "participants-container";
        const participantsHeading = document.createElement("h5");
        participantsHeading.textContent = "Participants";
        participants.appendChild(participantsHeading);
        if (details.participants.length === 0) {
          const emptyMessage = document.createElement("p");
          emptyMessage.textContent = "No participants yet";
          participants.appendChild(emptyMessage);
        } else {
          const participantList = document.createElement("ul");
          participantList.className = "participants-list";
          details.participants.forEach((email) => {
            const listItem = document.createElement("li");
            const participantEmail = document.createElement("span");
            participantEmail.textContent = email;
            listItem.appendChild(participantEmail);
            if (currentUser?.role === "student" && email === currentUser.email) {
              const unregisterButton = document.createElement("button");
              unregisterButton.type = "button";
              unregisterButton.textContent = "Unregister";
              unregisterButton.addEventListener("click", () =>
                handleUnregister(name)
              );
              listItem.appendChild(unregisterButton);
            }
            participantList.appendChild(listItem);
          });
          participants.appendChild(participantList);
        }
        activityCard.appendChild(participants);
        activitiesList.appendChild(activityCard);

        const option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        activitySelect.appendChild(option);
      });
    } catch (error) {
      activitiesList.textContent =
        "Failed to load activities. Please try again later.";
      console.error("Error fetching activities:", error);
    }
  }

  async function handleUnregister(activity) {
    try {
      const response = await fetch(
        `/activities/${encodeURIComponent(activity)}/unregister`,
        { method: "DELETE" }
      );
      const result = await response.json();
      if (!response.ok) {
        if (response.status === 401) {
          showLoggedOut();
          await fetchActivities();
        }
        showMessage(result.detail || "An error occurred", "error");
        return;
      }
      await fetchActivities();
      showMessage(result.message, "success");
    } catch (error) {
      showMessage("Failed to unregister. Please try again.", "error");
      console.error("Error unregistering:", error);
    }
  }

  async function submitCredentials(event, form, endpoint) {
    event.preventDefault();
    try {
      const prefix = form.id === "login-form" ? "login" : "register";
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: document.getElementById(`${prefix}-email`).value,
          password: document.getElementById(`${prefix}-password`).value,
        }),
      });
      const result = await response.json();
      if (!response.ok) {
        showMessage(result.detail || "An error occurred", "error");
        return;
      }
      form.reset();
      await updateAuthState();
      await fetchActivities();
      showMessage("Signed in successfully.", "success");
    } catch (error) {
      showMessage("Could not complete authentication. Please try again.", "error");
      console.error("Error authenticating:", error);
    }
  }

  loginForm.addEventListener("submit", (event) =>
    submitCredentials(event, loginForm, "/auth/login")
  );
  registerForm.addEventListener("submit", (event) =>
    submitCredentials(event, registerForm, "/auth/register")
  );

  logoutButton.addEventListener("click", async () => {
    try {
      const response = await fetch("/auth/logout", { method: "POST" });
      if (!response.ok) {
        throw new Error("Sign out request failed");
      }
      showLoggedOut();
      await fetchActivities();
      showMessage("Signed out.", "success");
    } catch (error) {
      showMessage("Could not sign out. Please try again.", "error");
      console.error("Error signing out:", error);
    }
  });

  signupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const activity = activitySelect.value;
      const response = await fetch(
        `/activities/${encodeURIComponent(activity)}/signup`,
        { method: "POST" }
      );
      const result = await response.json();
      if (!response.ok) {
        if (response.status === 401) {
          showLoggedOut();
          await fetchActivities();
        }
        showMessage(result.detail || "An error occurred", "error");
        return;
      }
      signupForm.reset();
      await fetchActivities();
      showMessage(result.message, "success");
    } catch (error) {
      showMessage("Failed to sign up. Please try again.", "error");
      console.error("Error signing up:", error);
    }
  });

  updateAuthState()
    .then(fetchActivities)
    .catch((error) => {
      showMessage("Could not check the signed-in account.", "error");
      console.error("Error checking account:", error);
      fetchActivities();
    });
});
