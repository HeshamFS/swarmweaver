"""
Hook definitions: security, management, marathon, audit.

Re-exports all hooks from main_hooks.py for backward-compatible imports
like `from hooks import bash_security_hook`.
"""
from hooks.main_hooks import (
    # Security hook (re-exported from hooks.security)
    bash_security_hook,
    # Protect SwarmWeaver backend from agent's kill-on-port commands
    protect_swarmweaver_backend_hook,
    # Autonomous management hooks
    server_management_hook,
    environment_management_hook,
    file_management_hook,
    port_config_hook,
    test_script_port_hook,
    knowledge_injection_hook,
    log_consolidation_hook,
    progress_file_management_hook,
    shell_script_lf_hook,
    # Write safety
    write_before_read_hook,
    # Steering hook
    steering_hook,
    worker_scope_hook,
    # Lifecycle hooks
    audit_log_hook,
    stop_hook,
    pre_compact_hook,
    subagent_stop_hook,
    # Mail injection
    mail_injection_hook,
    # Configuration functions
    set_audit_log_path,
    set_transcript_archive_path,
    set_stop_callback,
    set_project_dir,
    set_cleanup_on_stop,
    set_notification_callback,
    set_mail_store,
)
