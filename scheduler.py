import schedule
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("Scheduler")

def run_scan():
    log.info("Scheduled scan triggered")
    try:
        from jax_lead_scanner import run_all_agents
        total = run_all_agents()
        log.info(f"Scan complete — {total} leads generated")
    except Exception as e:
        log.error(f"Scan failed: {e}", exc_info=True)

if __name__ == "__main__":
    log.info("LeadForge Scheduler — Starting")
    run_scan()
    schedule.every(30).minutes.do(run_scan)
    while True:
        schedule.run_pending()
        time.sleep(60)
