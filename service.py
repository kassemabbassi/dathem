"""Windows service that supervises the interactive DATHEM Agent V1.

The service runs in Session 0. It must therefore launch the desktop agent in the
active user's session; the camera and DATHEM Tkinter screen stay in that
interactive process.
"""

import os
import sys
import time
import ctypes
import logging

import win32con
import win32api
import win32event
import win32process
import win32profile
import win32service
import win32serviceutil
import win32ts
import servicemanager


SERVICE_NAME = "DathemAgentV1"
AGENT_EXE = os.path.join("DathemAgentV1Agent", "DathemAgentV1Agent.exe")
POLL_SECONDS = 3
RESTART_DELAY_SECONDS = 5
EXIT_CODE_STILL_ACTIVE = 259
INVALID_SESSION_ID = 0xFFFFFFFF


def application_directory():
    if getattr(sys, "frozen", False):
        executable_directory = os.path.dirname(os.path.abspath(sys.executable))
        # In a distributable onedir build, PyInstaller places the service
        # executable in its own subdirectory while the desktop agent sits in
        # the package root beside that directory. Keep supporting the earlier
        # onefile layout where both are directly in the package root.
        if os.path.isdir(os.path.join(executable_directory, "DathemAgentV1Agent")):
            return executable_directory
        package_directory = os.path.dirname(executable_directory)
        if os.path.isdir(os.path.join(package_directory, "DathemAgentV1Agent")):
            return package_directory
        return executable_directory
    return os.path.dirname(os.path.abspath(__file__))


def active_console_session_id():
    # This Kernel32 API is available on Windows 10 and avoids depending on
    # pywin32 versions that may or may not expose the same helper.
    session_id = ctypes.windll.kernel32.WTSGetActiveConsoleSessionId()
    if session_id == INVALID_SESSION_ID:
        return None
    return int(session_id)


class DathemAgentV1Service(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = "DATHEM Agent V1"
    _svc_description_ = (
        "Supervises the DATHEM Agent V1 desktop agent in the active user session."
    )

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.agent_process = None
        self.agent_session_id = None
        self.profile_warning_session = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)

    def _stop_agent(self):
        process = self.agent_process
        self.agent_process = None
        self.agent_session_id = None
        if process is None:
            return
        try:
            exit_code = win32process.GetExitCodeProcess(process)
            if exit_code == EXIT_CODE_STILL_ACTIVE:
                win32process.TerminateProcess(process, 0)
                result = win32event.WaitForSingleObject(process, 5000)
                if result != win32event.WAIT_OBJECT_0:
                    logging.error("Timed out waiting for the desktop agent to exit")
        except Exception:
            logging.exception("Could not stop the desktop agent")
        finally:
            try:
                win32api_close_handle(process)
            except Exception:
                logging.exception("Could not close the agent process handle")

    def _launch_agent(self, session_id):
        agent_path = os.path.join(application_directory(), AGENT_EXE)
        if not os.path.isfile(agent_path):
            logging.error("Agent executable not found: %s", agent_path)
            return

        token = None
        environment = None
        process = None
        thread = None
        try:
            token = win32ts.WTSQueryUserToken(session_id)
            environment = win32profile.CreateEnvironmentBlock(token, False)
            local_app_data = environment.get("LOCALAPPDATA") or environment.get("USERPROFILE")
            profile_path = os.path.join(
                local_app_data, "DathemAgentV1", "profile.json"
            ) if local_app_data else None
            if profile_path is None or not os.path.isfile(profile_path):
                if self.profile_warning_session != session_id:
                    logging.warning(
                        "No DATHEM profile for session %s; run DathemAgentV1Setup.exe first",
                        session_id,
                    )
                    self.profile_warning_session = session_id
                return
            self.profile_warning_session = None
            startup = win32process.STARTUPINFO()
            startup.lpDesktop = r"winsta0\default"
            command_line = '"{}"'.format(agent_path)
            flags = win32con.CREATE_UNICODE_ENVIRONMENT | win32con.CREATE_NEW_PROCESS_GROUP
            process, thread, _, _ = win32process.CreateProcessAsUser(
                token,
                agent_path,
                command_line,
                None,
                None,
                False,
                flags,
                environment,
                application_directory(),
                startup,
            )
            self.agent_process = process
            self.agent_session_id = session_id
            process = None  # Ownership transferred to self.agent_process.
            logging.info("Started desktop agent in session %s", session_id)
        except Exception:
            logging.exception("Could not launch agent in session %s", session_id)
        finally:
            for handle in (thread, process, token):
                if handle is not None:
                    try:
                        win32api_close_handle(handle)
                    except Exception:
                        logging.exception("Could not close a launch handle")
    def SvcDoRun(self):
        logging.basicConfig(
            filename=os.path.join(application_directory(), "DathemAgentV1-service.log"),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        last_launch_attempt = 0.0

        while win32event.WaitForSingleObject(self.stop_event, POLL_SECONDS * 1000) == win32event.WAIT_TIMEOUT:
            session_id = active_console_session_id()
            if session_id != self.agent_session_id:
                self._stop_agent()

            if session_id is None:
                continue

            if self.agent_process is not None:
                try:
                    if win32process.GetExitCodeProcess(self.agent_process) != EXIT_CODE_STILL_ACTIVE:
                        logging.warning("Desktop agent exited; it will be restarted")
                        self._stop_agent()
                except Exception:
                    logging.exception("Could not inspect the desktop agent")
                    self._stop_agent()

            now = time.monotonic()
            if self.agent_process is None and now - last_launch_attempt >= RESTART_DELAY_SECONDS:
                last_launch_attempt = now
                self._launch_agent(session_id)

        self._stop_agent()


def win32api_close_handle(handle):
    # CloseHandle works for process, thread, and token handles returned above.
    win32api.CloseHandle(handle)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # The Service Control Manager starts a frozen executable without the
        # command-line verb used for install/start/stop. Enter the native
        # service dispatcher explicitly in that case.
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(DathemAgentV1Service)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(DathemAgentV1Service)
