# ======================== Imports ========================
from datetime import datetime
from typing import Optional
failed_imports=[]
try:
    import colorama as color #Try catch due to colors being an optional feature that should not be enforced
except:
    failed_imports.append("colorama")


# ======================== Independent Functions ========================

def emphasize_string(s):
        return color.Fore.CYAN + color.Style.BRIGHT + str(s) + color.Fore.RESET + color.Style.RESET_ALL

def emphasize_err_string(s):
        return color.Fore.RED + color.Style.BRIGHT + str(s) + color.Fore.RESET + color.Style.RESET_ALL

def logger_logger(msg: str, logger_name: str):
    """Simple internal debug printer used by the logger for diagnostics.

    This function is intended for internal debug output from the logging
    implementation itself (not end-user log messages). It prints a fixed
    prefix including the logger name.

    Args:
        msg (str): Diagnostic message to print.
        logger_name (str): Name of the logger emitting the diagnostic.
    """
    print(f"[LOGGER_DEBUG][{logger_name}]; {msg}")


# ======================== Logger Class ========================
class LoggerClass:

    def __init__(self, logger_name: str = 'UNNAMED_LOGGER',logger_level: int=1,
                 log_date: bool = False, log_time: bool = True, log_name: bool = True,
                 log_function: bool = True,log_level: bool = True, log_color: bool = True, logger_debug: bool = False
                 ):
        """Create a LoggerClass instance with formatting options.

        The logger only prints messages whose severity is >= `logger_level`.

        Args:
            logger_name (str): Human-readable name included in each message.
            logger_level (int): Minimum level to show (0=DEBUG .. 5=ERROR).
            log_date (bool): Include the date in the prefix when True.
            log_time (bool): Include the time in the prefix when True.
            log_name (bool): Include the logger name in the prefix when True.
            log_function (bool): If True include the calling function name in
                the prefix.
            log_level (bool): Include the textual log level when True.
            log_color (bool): Use colored output when True and colorama is
                available.
            logger_debug (bool): If True, enable internal debug diagnostics
                from the logger implementation itself.


        Attributes:
            logger_name, logger_level, log_date, log_time, log_name,
            log_level, log_color, prevent_color, logger_debug, log_function
                Stored configuration used by other methods.
        """
        if logger_debug:
            self.logger_debug = True
            logger_logger(f"Debug Mode for Logger: {logger_name} set to: True", logger_name)
            logger_logger(
                f"args: logger_name={logger_name}, logger_level={logger_level}, log_date={log_date}, log_time={log_time}, log_name={log_name}, log_level={log_level},log_color={log_color} logger_debug={logger_debug}",
                logger_name)

        if logger_level - 5 > 0:
            print(
                f"[Logger_ERROR]; Invalid logger_level {logger_level} for logger {logger_name} setting using default 2")
            logger_level = 0

        prevent_color = False
        if "colorama" in failed_imports and log_color:
            logger_logger("Color is enabled", logger_name)
            prevent_color = True
            log_color = False

        self.logger_name = logger_name
        self.logger_level = logger_level
        self.log_date = log_date
        self.log_time = log_time
        self.log_name = log_name
        self.log_function = log_function
        self.log_level = log_level
        self.log_color = log_color
        self.prevent_color = prevent_color
        self.logger_debug = logger_debug



    def _get_caller_name(self) -> str:
        """Return the name of the first caller outside the LoggerClass.

        Uses the inspect stack to find the first frame that is not bound to a
        LoggerClass instance and returns its function name. If no such frame
        is found, returns "<module>".

        Returns:
            str: Caller function name or "<module>" when called from top-level.
        """
        import inspect
        for frame_info in inspect.stack()[1:]:
            f_locals = frame_info.frame.f_locals
            if 'self' in f_locals and isinstance(f_locals['self'], LoggerClass):
                continue
            return frame_info.function
        return "<module>"

    def logger_log(self, msg):
        """Emit an internal logger diagnostic message when internal debugging is enabled.

        This is a thin helper that forwards to the module-level `logger_logger`
        if `self.logger_debug` is True.

        Args:
            msg (str): Diagnostic message to emit.
        """
        if self.logger_debug:
            logger_logger(msg, logger_name = self.logger_name)

    def construct_prefix(self, message_log_level: int = 1, log_date: Optional[bool] = None,
                         log_time: Optional[bool] = None, log_name: Optional[bool] = None,
                         log_level: Optional[bool] = None, log_color: Optional[bool] = None,
                         log_function: Optional[bool] = None) -> str:
        """Build the textual prefix used for log messages.

        The prefix is composed of optional parts (date/time, logger name,
        calling function and textual level). The effective options are
        determined by falling back to the instance configuration when the
        corresponding parameter is None.

        Args:
            message_log_level (int): Severity level for the message (0..5).
            log_date (Optional[bool]): Override instance `log_date` if provided.
            log_time (Optional[bool]): Override instance `log_time` if provided.
            log_name (Optional[bool]): Override instance `log_name` if provided.
            log_level (Optional[bool]): Override instance `log_level` if provided.
            log_color (Optional[bool]): Override instance `log_color` if provided.
            log_function (Optional[bool]): Override instance `log_function` if provided.

        Returns:
            str: Formatted prefix that should be prepended to the log message.
        """
        if log_date is None:
            log_date = self.log_date
        if log_time is None:
            log_time = self.log_time
        if log_name is None:
            log_name = self.log_name
        if log_level is None:
            log_level = self.log_level
        if log_color is None:
            log_color = self.log_color
        if log_function is None:
            log_function = self.log_function
        levels = [" DEBUG ", " VALUE ", "  INFO ", "SUCCESS", "WARNING", " ERROR "," FATAL "]
        if message_log_level - len(levels) > 0:
            logger_logger(f"Encountered invalid message_log_level: {message_log_level} during prefix construction",
                          self.logger_name)

        if not self.prevent_color and log_color:
            levels = [color.Fore.RESET + ' DEBUG ' + color.Fore.RESET,
                      color.Fore.MAGENTA + ' VALUE ' + color.Fore.RESET,
                      color.Fore.CYAN + ' INFO  ' + color.Fore.RESET,
                      color.Fore.LIGHTGREEN_EX + 'SUCCESS' + color.Fore.RESET,
                      color.Fore.YELLOW + 'WARNING' + color.Fore.RESET,
                      color.Fore.LIGHTRED_EX + color.Style.BRIGHT + ' ERROR ' + color.Style.RESET_ALL,
                      color.Back.RED + color.Style.BRIGHT + color.Fore.BLACK + ' FATAL ' + color.Style.RESET_ALL
                      ]

        time = datetime.now()
        parts = []

        if log_date and log_time:
            parts.append(f"[{time.strftime('%d-%m-%Y')} {time.strftime('%H:%M:%S')}.{time.microsecond // 1000:03d}]")
        elif log_date:
            parts.append(f"[{time.strftime('%d-%m-%Y')}]")
        elif log_time:
            parts.append(f"[{time.strftime('%H:%M:%S')}.{time.microsecond // 1000:03d}]")
        if log_name:
            lname=f"{self.logger_name}"
            parts.append(f"[{lname:<20}]")
        if log_function:
            parts.append(f"[{self._get_caller_name():<20}]")
        if log_level:
            parts.append(f"[{levels[message_log_level]}]")
        return f"{' '.join(parts)}; "

    def log_message(self, msg: str, log_level: int):
        """Log a message to stdout if its level meets the logger threshold.

        The message is formatted using :meth:`construct_prefix` and printed to
        standard output. Messages with `log_level` lower than the instance
        `logger_level` are discarded.

        Args:
            msg (str): Message body to log.
            log_level (int): Severity level for the message (0..5).
        """
        if log_level < self.logger_level:
            if self.logger_debug: logger_logger(
                f"log level {log_level} is lower than set logger level {self.logger_level}. Message will be discarded",
                self.logger_name)
            return
        log_message = f"{self.construct_prefix(log_level)}{msg}"
        print(log_message)

    def debug(self, msg: str):
        """Log a DEBUG level message (level 0).

        Args:
            msg (str): Message body.
        """
        self.log_message(msg, 0)

    def value(self, msg: str):
        """Log a VALUE level message (level 1).

        Args:
            msg (str): Message body.
        """
        self.log_message(msg, 1)

    def info(self, msg: str):
        """Log an INFO level message (level 2).

        Args:
            msg (str): Message body.
        """
        self.log_message(msg, 2)

    def success(self, msg: str):
        """Log a SUCCESS level message (level 3).

        Args:
            msg (str): Message body.
        """
        self.log_message(msg, 3)

    def warning(self, msg):
        """Log a WARNING level message (level 4).

        Args:
            msg: Message body (converted to str when formatted).
        """
        self.log_message(msg, 4)

    def error(self, msg):
        """Log an ERROR level message (level 5).

        Args:
            msg: Message body (converted to str when formatted).
        """
        self.log_message(msg, 5)
    
    def fatal(self,msg):
        """Log an ERROR level message (level 5).

        Args:
            msg: Message body (converted to str when formatted).
        """
        self.log_message(msg,6)