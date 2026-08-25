"""Not a pytest test — this hits real GCP infrastructure. Run manually
after `agents-cli deploy` to confirm D4/D5/D6 actually landed."""
import os
import sys
import vertexai

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
AGENT_ENGINE_ID = os.environ["AGENT_ENGINE_ID"]


def main():
    client = vertexai.Client(project=PROJECT, location=LOCATION)
    agent = client.agent_engines.get(AGENT_ENGINE_ID)
    print(f"[D4] Agent Runtime resource state: {agent.state}")
    assert agent.state == "ACTIVE", "agent is not deployed to Agent Runtime"

    # D5: Agent Registry auto-registration.
    import subprocess
    result = subprocess.run(
        ["gcloud", "agent-registry", "agents", "list",
         f"--project={PROJECT}", f"--location={LOCATION}"],
        capture_output=True, text=True,
    )
    print(f"[D5] Agent Registry listing:\n{result.stdout}")
    assert AGENT_ENGINE_ID in result.stdout, "agent did not auto-register in Agent Registry"

    print("[D6] Reminder: open Cloud Trace / the platform's Unified Trace Viewer "
          "and confirm spans are arriving for a real invocation — this script "
          "cannot assert that without making a live, billed call.")


if __name__ == "__main__":
    sys.exit(main())
