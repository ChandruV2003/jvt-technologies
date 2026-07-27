const navToggle = document.querySelector(".nav-toggle");
const siteNav = document.querySelector(".site-nav");
const yearTarget = document.querySelector("#current-year");
const header = document.querySelector(".site-header");
const intakeForm = document.querySelector("#workflow-intake-form");
const intakeStatus = document.querySelector("#workflow-intake-status");
const intakeSubmissionId = document.querySelector("#workflow-submission-id");

if (navToggle && siteNav) {
  navToggle.addEventListener("click", () => {
    const isOpen = siteNav.classList.toggle("is-open");
    navToggle.setAttribute("aria-expanded", String(isOpen));
  });

  siteNav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      siteNav.classList.remove("is-open");
      navToggle.setAttribute("aria-expanded", "false");
    });
  });
}

const reveals = document.querySelectorAll(".reveal");

window.addEventListener("scroll", () => {
  if (!header) {
    return;
  }

  if (window.scrollY > 24) {
    header.classList.add("is-scrolled");
  } else {
    header.classList.remove("is-scrolled");
  }
});

if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.18 },
  );

  reveals.forEach((node) => observer.observe(node));
} else {
  reveals.forEach((node) => node.classList.add("is-visible"));
}

if (yearTarget) {
  yearTarget.textContent = String(new Date().getFullYear());
}

const INTAKE_SESSION_KEY = "jvt-public-workflow-intake-id";

function makeSubmissionId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return `wfintake_${window.crypto.randomUUID().replace(/-/g, "")}`;
  }

  const randomPart = Math.random().toString(36).slice(2, 12);
  return `wfintake_${Date.now().toString(36)}_${randomPart}`;
}

function getSubmissionId() {
  try {
    const existing = window.sessionStorage.getItem(INTAKE_SESSION_KEY);
    if (existing) {
      return existing;
    }
    const created = makeSubmissionId();
    window.sessionStorage.setItem(INTAKE_SESSION_KEY, created);
    return created;
  } catch {
    return makeSubmissionId();
  }
}

function attributionPayload() {
  const params = new URLSearchParams(window.location.search);
  return {
    source: "public-site-workflow-intake",
    source_url: window.location.href,
    page_path: `${window.location.pathname}${window.location.hash || ""}`,
    referrer: document.referrer || "",
    utm_source: params.get("utm_source") || "",
    utm_medium: params.get("utm_medium") || "",
    utm_campaign: params.get("utm_campaign") || "",
    utm_term: params.get("utm_term") || "",
    utm_content: params.get("utm_content") || "",
  };
}

async function postIntakePayload(payload) {
  const response = await fetch("/api/workflow-intake", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    throw new Error(data.message || "The workflow note could not be saved.");
  }
  return data;
}

function setIntakeStatus(message, state = "") {
  if (!intakeStatus) {
    return;
  }
  intakeStatus.textContent = message;
  intakeStatus.classList.toggle("is-error", state === "error");
  intakeStatus.classList.toggle("is-success", state === "success");
}

if (intakeForm && intakeSubmissionId) {
  let submissionId = getSubmissionId();
  let viewRecorded = false;
  let startRecorded = false;
  intakeSubmissionId.value = submissionId;

  const rotateSubmissionId = () => {
    submissionId = makeSubmissionId();
    try {
      window.sessionStorage.setItem(INTAKE_SESSION_KEY, submissionId);
    } catch {
      // The in-memory identifier is still enough for this page session.
    }
    intakeSubmissionId.value = submissionId;
    startRecorded = false;
  };

  const recordIntakeEvent = async (eventType) => {
    try {
      await postIntakePayload({
        event_type: eventType,
        submission_id: submissionId,
        service_interest: new FormData(intakeForm).get("service_interest") || "",
        ...attributionPayload(),
      });
    } catch {
      // Metric capture is useful but non-blocking for the prospect.
    }
  };

  const markStarted = () => {
    if (startRecorded) {
      return;
    }
    startRecorded = true;
    recordIntakeEvent("start");
  };

  intakeForm.addEventListener("focusin", markStarted);
  intakeForm.addEventListener("input", markStarted, { once: true });
  intakeForm.addEventListener("change", markStarted, { once: true });

  if ("IntersectionObserver" in window) {
    const intakeObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!viewRecorded && entry.isIntersecting) {
            viewRecorded = true;
            recordIntakeEvent("view");
            intakeObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.35 },
    );
    intakeObserver.observe(intakeForm);
  } else {
    viewRecorded = true;
    recordIntakeEvent("view");
  }

  intakeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    markStarted();
    if (!intakeForm.reportValidity()) {
      setIntakeStatus("Please fill in the required fields first.", "error");
      return;
    }

    const submitButton = intakeForm.querySelector("button[type='submit']");
    const formData = new FormData(intakeForm);
    const payload = {
      submission_id: submissionId,
      name: formData.get("name") || "",
      public_business_email: formData.get("public_business_email") || "",
      company: formData.get("company") || "",
      service_interest: formData.get("service_interest") || "",
      problem_description: formData.get("problem_description") || "",
      preferred_next_step: formData.get("preferred_next_step") || "",
      ...attributionPayload(),
    };

    setIntakeStatus("Saving...");
    if (submitButton) {
      submitButton.disabled = true;
    }

    try {
      const result = await postIntakePayload(payload);
      setIntakeStatus(result.message || "Received. JVT will review it before any follow-up.", "success");
      intakeForm.reset();
      rotateSubmissionId();
    } catch (error) {
      setIntakeStatus(`${error.message} Email hello@jvt-technologies.com if this keeps failing.`, "error");
    } finally {
      if (submitButton) {
        submitButton.disabled = false;
      }
    }
  });
}
