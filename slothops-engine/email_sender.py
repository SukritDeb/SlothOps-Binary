import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

logger = logging.getLogger("slothops.qa.email")

def send_qa_report_email(
    qa_report: dict,
    recipient_email: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str
) -> bool:
    """Send a formatted HTML email with the QA report summary."""
    if not recipient_email or not smtp_host:
        logger.warning("Email configuration missing. Skipping QA report email.")
        return False
        
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"SlothOps QA Report: PR #{qa_report.get('pr_number', 'Unknown')}"
        msg["From"] = smtp_user
        msg["To"] = recipient_email
        
        status_color = "green"
        if qa_report.get("overall_status") == "failed":
            status_color = "red"
        elif qa_report.get("overall_status") == "warning":
            status_color = "orange"
            
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 8px;">
                <h2 style="color: {status_color};">SlothOps QA Report</h2>
                <p><strong>PR:</strong> <a href="{qa_report.get('pr_url', '#')}">#{qa_report.get('pr_number', 'N/A')}</a></p>
                <p><strong>Repository:</strong> {qa_report.get('repo_name', 'N/A')}</p>
                <p><strong>Status:</strong> <span style="color: {status_color}; font-weight: bold;">{qa_report.get('overall_status', 'N/A').upper()}</span></p>
                
                <div style="margin-top: 20px; padding: 15px; background: #f9f9f9; border-radius: 5px;">
                    <h3>Execution Summary</h3>
                    <p style="white-space: pre-wrap;">{qa_report.get('summary', 'No summary available.')}</p>
                </div>
                
                <p style="margin-top: 30px; font-size: 0.9em; color: #777;">
                    View full details in the SlothOps Dashboard.
                </p>
            </div>
        </body>
        </html>
        """
        
        part = MIMEText(html, "html")
        msg.attach(part)
        
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, recipient_email, msg.as_string())
        server.quit()
        
        logger.info("Successfully sent QA report email to %s", recipient_email)
        return True
    except Exception as e:
        logger.error("Failed to send QA report email: %s", e)
        return False

def send_rollback_notification_email(
    rollback_info: dict,
    recipient_email: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str
) -> bool:
    """Send an email notifying about an automatic production rollback."""
    if not recipient_email or not smtp_host:
        logger.warning("Email configuration missing. Skipping rollback email.")
        return False
        
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🚨 SlothOps Auto-Rollback: {rollback_info.get('repo_name', 'Repository')}"
        msg["From"] = smtp_user
        msg["To"] = recipient_email
            
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ef4444; border-radius: 8px;">
                <h2 style="color: #ef4444;">🚨 Automatic Production Rollback</h2>
                <p>SlothOps detected a production deployment failure and automatically reverted the bad commit to restore stability.</p>
                
                <p><strong>Repository:</strong> {rollback_info.get('repo_name', 'N/A')}</p>
                <p><strong>Failed Commit:</strong> <code>{rollback_info.get('failed_sha', 'N/A')}</code></p>
                <p><strong>Reason:</strong> {rollback_info.get('failure_reason', 'Deployment failed')}</p>
                
                <div style="margin-top: 20px; padding: 15px; background: #fef2f2; border: 1px solid #fca5a5; border-radius: 5px;">
                    <h3 style="color: #b91c1c; margin-top: 0;">Backup Branch Created</h3>
                    <p>The failing changes have been preserved in a backup branch so you can debug and fix the issue:</p>
                    <p><code>{rollback_info.get('backup_branch', 'N/A')}</code></p>
                </div>
                
                <p style="margin-top: 30px; font-size: 0.9em; color: #777;">
                    View full details in the SlothOps Dashboard.
                </p>
            </div>
        </body>
        </html>
        """
        
        part = MIMEText(html, "html")
        msg.attach(part)
        
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, recipient_email, msg.as_string())
        server.quit()
        
        logger.info("Successfully sent rollback email to %s", recipient_email)
        return True
    except Exception as e:
        logger.error("Failed to send rollback email: %s", e)
        return False

def send_resolution_notification_email(
    resolution_info: dict,
    recipient_email: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str
) -> bool:
    """Send an email notifying that SlothOps generated a fix for a failed deployment."""
    if not recipient_email or not smtp_host:
        logger.warning("Email configuration missing. Skipping resolution email.")
        return False
        
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🔧 SlothOps Auto-Resolution: Fix PR Opened for {resolution_info.get('repo_name', 'Repository')}"
        msg["From"] = smtp_user
        msg["To"] = recipient_email
            
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #3b82f6; border-radius: 8px;">
                <h2 style="color: #3b82f6;">🔧 Auto-Resolution PR Opened</h2>
                <p>Following a recent automatic rollback, SlothOps has analyzed the build error and generated a fix (Attempt <b>{resolution_info.get('attempt_number', 1)}</b>).</p>
                
                <p><strong>Repository:</strong> {resolution_info.get('repo_name', 'N/A')}</p>
                <p><strong>Backup Branch:</strong> <code>{resolution_info.get('backup_branch', 'N/A')}</code></p>
                
                <div style="margin-top: 20px; padding: 15px; background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 5px;">
                    <h3>Build Error Excerpt</h3>
                    <p style="white-space: pre-wrap; font-family: monospace; font-size: 0.9em; overflow-x: auto;">{resolution_info.get('build_error_log', 'No log available')[:500]}...</p>
                </div>
                
                <a href="{resolution_info.get('pr_url', '#')}" style="display: inline-block; margin-top: 25px; padding: 10px 20px; background-color: #3b82f6; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">Review Auto-Fix PR</a>
                
                <p style="margin-top: 30px; font-size: 0.9em; color: #777;">
                    If this CI build fails again, SlothOps will automatically perform a re-cycle (up to 3 times) to resolve the issue.
                </p>
            </div>
        </body>
        </html>
        """
        
        part = MIMEText(html, "html")
        msg.attach(part)
        
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, recipient_email, msg.as_string())
        server.quit()
        
        logger.info("Successfully sent resolution email to %s", recipient_email)
        return True
    except Exception as e:
        logger.error("Failed to send resolution email: %s", e)
        return False


