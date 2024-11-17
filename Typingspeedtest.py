import customtkinter as ctk
from tkinter import StringVar, messagebox
import datetime
import random


def main():
    app = TypingSpeedApp("dark")  # set up here the app 'mode': light / dark
    app.mainloop()


class TypingSpeedApp(ctk.CTk):
    def __init__(self, mode):
        super().__init__()

        ctk.set_appearance_mode(mode)
        self.title("Typing Speed Test")
        self.geometry("1200x700+80+20")
        self.minsize(800, 600)

        self.grid_rowconfigure((0, 1), weight=1, uniform="a")
        self.grid_columnconfigure(0, weight=4)
        self.grid_columnconfigure(1, weight=1)

        self.system = SystemText(self)
        self.user = UserText(self, self.check_point)

        # Initialize key app data
        self.timer_id = None
        self.timer_on = True
        self.test_number = 0
        self.sys_chars_list = []
        self.user_chars_list = []
        self.test_time_requested = 0
        self.test_time_elapsed = 0
        self.user_char_count = 0
        self.char_err_count = 0
        self.accuracy = 0.0
        self.CPM_score = 0
        self.WPM_score = 0

        self.setup = TestSetup(self, self.start_test, self.stop_test)
        self.load_sys_textbox()

        self.results = TestResults(self, self.result_details)

        self.details = ResultDetails(self)

        self.widgets_off_test()  # initialize widgets' state ready for a first test

        self.protocol("WM_DELETE_WINDOW", self.close_app)

    def widgets_off_test(self):
        """Disable / enable widgets if no test is running"""
        self.setup.start_test_btn.configure(state="normal")
        self.setup.stop_test_btn.configure(state="disabled")
        self.setup.difficulty.configure(state="normal")
        self.setup.test_time.configure(state="normal")
        self.user.user_textbox.configure(state="disabled")
        self.results.details_btn.configure(state="normal")

    def widgets_on_test(self):
        """Disable / enable widgets while test is on"""
        self.setup.start_test_btn.configure(state="disabled")
        self.setup.stop_test_btn.configure(state="normal")
        self.setup.difficulty.configure(state="disabled")
        self.setup.test_time.configure(state="disabled")
        self.user.user_textbox.configure(state="normal")
        self.results.details_btn.configure(state="disabled")

    def load_sys_textbox(self):
        # Load system's textbox with text according to difficulty selected
        self.system.sys_textbox.configure(state="normal")
        if self.system.sys_textbox.get("1.0", "end-1c") != "":
            self.system.sys_textbox.delete("1.0", "end")

        text_to_insert = self.setup.read_text_file()
        self.system.sys_textbox.insert("1.0", text_to_insert)
        self.system.sys_textbox.configure(state="disabled")

        # Empty the user's textbox as the system's textbox has been updated
        if self.user.user_textbox.get("1.0", "end-1c") != "":
            self.user.user_textbox.configure(state="normal")
            self.user.user_textbox.delete("1.0", "end")
            self.user.user_textbox.configure(state="disabled")
            self.user.timer_label.configure(text="00:00")

    def start_test(self):
        self.widgets_on_test()  # Disable / enable widgets until test is finalized
        self.timer_on = True
        self.test_number += 1

        # Ensure user's textbox starts out empty for the new test
        if self.user.user_textbox.get("1.0", "end-1c") != "":
            self.user.user_textbox.delete("1.0", "end")
        self.user.user_textbox.focus_set()

        # Start timer
        self.test_time_requested = int(self.setup.test_time_var.get())
        self.test_timer(self.test_time_requested)

    def test_timer(self, t):
        """Start countdown from user requested time down to zero or to the user's stop request.
        Register effective elapsed time (in proportion to which calculate CPM and WPM) and process test results.
        """
        if t >= 0:
            mins, secs = divmod(t, 60)
            timer = "{:02d}:{:02d}".format(mins, secs)  # for an MM:SS format

            if t > 15:
                self.user.timer_label.configure(
                    text=timer, text_color=("green", "yellow")
                )
            elif t > 5:
                self.user.timer_label.configure(text=timer, text_color="orange")
            else:
                self.user.timer_label.configure(text=timer, text_color="red")

            if not self.timer_on:  # User clicked on "Stop Test"
                self.test_time_elapsed = self.test_time_requested - t

                self.check_point()  # One last scan and processing of the user text

                self.after_cancel(self.timer_id)
                self.user.timer_label.configure(text_color="gray")
                self.setup.update_test_number(
                    self.test_number + 1
                )  # Alluding to a new (future) test
                self.widgets_off_test()
                # print(f"Time elapsed (timer stopped): {self.test_time_elapsed}")
                if (
                        self.test_time_elapsed > 0
                ):  # Can't compute results for a 0 sec test duration
                    self.get_test_results()
            else:  # Keep the countdown going
                self.timer_id = self.after(1000, self.test_timer, t - 1)
        else:  # Test is finalized
            self.test_time_elapsed = self.test_time_requested
            self.user.timer_label.configure(text_color="gray")
            self.setup.update_test_number(
                self.test_number + 1
            )  # Alluding to a new (future) test

            self.check_point()  # One last scan and processing of the user text

            self.widgets_off_test()
            self.get_test_results()

    def stop_test(self):
        self.timer_on = False  # Flag to have the timer stop

    def check_point(self, event=None):
        """On "space" keypress (and on exit) the accumulated text as typed by the user up to that point
        is compared to the reference text offered by the system on a character basis. If a char-based comparison
        fails, the user's char counts as an error and is marked (red + bold). Errors won't compute towards the
        end result of total number of chars per min (CPM). ("Raw CPM" would include these errors).
        (The international standard counts CPM, and estimates words per min - WPM - at an avg of 5 chars/word).
        """
        _, self.sys_chars_list = self.analyze_text(self.system.sys_textbox)
        # print(self.sys_chars_list)
        _, self.user_chars_list = self.analyze_text(self.user.user_textbox)
        # print(self.user_chars_list)

        # This is the key control in the test: a pairwise comparison of each user char against its system char reference
        self.char_err_count = 0
        for idx, (sys_char, user_char) in enumerate(
                zip(self.sys_chars_list, self.user_chars_list)
        ):
            if sys_char != user_char:
                self.char_err_count += 1
                self.mark_red(idx)
            else:
                self.unmark_red(idx)

    def analyze_text(self, textbox):
        """Turn a string of text (as captured from the tk widget, whether from the sys text
        or the user's) into a list of elements, both at the word and the character level.
        """
        text_to_analyze = textbox.get("1.0", "end-1c")  # a str
        words_list = text_to_analyze.split(" ")

        # To avoid recognizing as an additional (empty) word if the user's text ends w/ a space
        if words_list[-1] == "":
            words_list = words_list[:-1]

        # Prepare words to concatenate all chars with '_' as word separator
        words_list = [
            word + "_" if i < len(words_list) - 1 else word
            for i, word in enumerate(words_list)
        ]
        chars_list = [char for word in words_list for char in word]
        return words_list, chars_list

    def mark_red(self, idx):
        """Mark red and bold the char at position idx in user text (with tags previously configured)"""
        red_idx = "1." + str(idx)
        self.user.user_textbox.tag_add("go_red", red_idx)
        self.user.user_textbox.tag_add("go_bold", red_idx)

    def unmark_red(self, idx):
        """Unmark red and bold the char at position idx if there's been a correction"""
        red_idx = "1." + str(idx)
        self.user.user_textbox.tag_add("go_unred", red_idx)
        self.user.user_textbox.tag_add("go_unbold", red_idx)

    def get_test_results(self):
        """Grab the final CPM and WPM results and show them. Set up the additional Details popup window."""

        self.user_char_count = len(
            [char for char in self.user_chars_list if char != "_"]
        )  # To exclude spaces

        correct_char_count = self.user_char_count - self.char_err_count
        self.CPM_score = int(correct_char_count * 60 / self.test_time_elapsed)
        self.results.CPM.configure(text=str(self.CPM_score))
        try:
            self.accuracy = round((correct_char_count / self.user_char_count), 2) * 100
        except ZeroDivisionError:
            pass

        self.WPM_score = int(self.CPM_score / 5)
        self.results.WPM.configure(
            text=str(self.WPM_score),
            text_color="green",
        )

    def result_details(self):
        """Collect test data and handle popup window to show it"""

        self.details = ResultDetails(self)
        self.details.deiconify()  # To show the popup window (initially withdrawn)
        self.details.grab_set()  # To prevent inputs on main window app

        # Update test results data for popup
        self.details.raw_char_count.configure(text=self.user_char_count)
        self.details.error_count.configure(text=self.char_err_count, text_color="red")
        self.details.test_time.configure(text=self.test_time_elapsed)
        self.details.CPM.configure(text=str(self.CPM_score))
        self.details.WPM.configure(
            text=str(self.WPM_score),
            text_color="green",  # ? / olive green
        )
        self.details.accuracy.configure(text=f"{str(self.accuracy)}%")

    def close_app(self):
        abort_window = messagebox.askyesno(
            title="Exit app?", message="Are you sure you want to close this app?"
        )
        if abort_window:
            self.destroy()


class SystemText(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent)

        STD_FONT = ctk.CTkFont("Calibri", 14)
        TEXT_FONT = ctk.CTkFont("Arial", 18)
        TXTBX_COLOR = ("#c1e0c9", "#fad9db")  # Light green / Light pink

        self.configure(fg_color="transparent")

        self.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=3)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=4)

        ctk.CTkLabel(
            self,
            text="Reference text",
            font=STD_FONT,
            text_color=("black", "white"),
            # fg_color="gray",
        ).grid(row=0, column=0, padx=20, pady=(5, 0), sticky="sw")

        self.sys_textbox = ctk.CTkTextbox(
            self,
            width=600,
            height=200,
            text_color="black",
            fg_color=TXTBX_COLOR,
            corner_radius=10,
            wrap="word",
            font=TEXT_FONT,
        )
        self.sys_textbox.grid(
            row=1, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="nsew"
        )
        self.sys_textbox.configure(state="disabled")


class UserText(ctk.CTkFrame):
    def __init__(self, parent, check_callback):
        super().__init__(parent)

        STD_FONT = ctk.CTkFont("Calibri", 14)
        TEXT_FONT = ctk.CTkFont("Arial", 16)
        ERROR_TEXT_FONT = ctk.CTkFont("Arial", 16, "bold")
        TXTBX_COLOR = "white"

        self.configure(fg_color="transparent")

        self.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=3)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=4)
        self.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            self,
            text="Type your text here",
            font=STD_FONT,
            text_color=("black", "white"),
            # fg_color="gray",
        ).grid(row=0, column=0, padx=20, pady=(5, 0), sticky="sw")

        self.user_textbox = ctk.CTkTextbox(
            self,
            width=600,
            height=200,
            text_color="black",
            fg_color=TXTBX_COLOR,
            corner_radius=10,
            wrap="word",
            font=TEXT_FONT,
        )
        self.user_textbox.grid(
            row=1, column=0, columnspan=3, padx=10, pady=(0, 10), sticky="nsew"
        )

        # Prepare tags to apply markup format to error chars (and the reverse if a correction is made)
        self.user_textbox.tag_config("go_red", foreground="red")
        self.user_textbox.tag_config("go_bold", cnf={"font": ERROR_TEXT_FONT})
        self.user_textbox.tag_config("go_unred", foreground="black")
        self.user_textbox.tag_config("go_unbold", cnf={"font": TEXT_FONT})

        # Each keypress on the space key (signaling a typed word) triggers the main error-checking process
        self.user_textbox.bind("<KeyPress-space>", check_callback)

        # Timer
        self.timer_label = ctk.CTkLabel(
            self,
            text="00:00",
            font=("Courier", 36, "bold"),
            text_color="gray",
        )
        self.timer_label.grid(row=0, column=2, padx=10, pady=(10, 0), sticky="se")


class TestSetup(ctk.CTkFrame):
    def __init__(self, parent, start_callback, stop_callback):
        super().__init__(parent)

        self.main = parent

        STD_FONT = ctk.CTkFont("Arial", 12)
        BOLD_FONT = ctk.CTkFont("Arial", 16, "bold")

        self.grid(row=0, column=1, padx=10, pady=(10, 20), sticky="nsew")
        self.grid_rowconfigure(0, weight=2)
        self.grid_rowconfigure((1, 2, 3, 4), weight=1, uniform="a")
        self.grid_columnconfigure((0, 1), weight=1, uniform="a")

        # Setup frame label
        self.test_number = StringVar(value="Setup a new test: Test #1")
        ctk.CTkLabel(
            self,
            textvariable=self.test_number,
            font=BOLD_FONT,
            text_color=("black", "white"),
            # fg_color="gray",
        ).grid(
            row=0,
            column=0,
            padx=10,
            columnspan=2,
            pady=(10, 0),
            ipadx=10,
            ipady=2,
            sticky="nw",
        )

        # Text difficulty selector
        self.difficulty_label = ctk.CTkLabel(
            self,
            text="Text difficulty",
            font=STD_FONT,
            text_color=("black", "white"),
            # fg_color="gray",
        )
        self.difficulty_label.grid(
            row=1, column=0, padx=10, pady=(10, 5), ipadx=5, sticky="se"
        )

        self.difficulty_var = StringVar(value="Medium")
        self.difficulty = ctk.CTkComboBox(
            self,
            values=["Medium", "High"],
            variable=self.difficulty_var,
            command=self.difficulty_selected,
        )
        self.difficulty.grid(
            row=1, column=1, padx=10, pady=(10, 5), ipadx=10, sticky="sw"
        )

        # Test time requested by user
        self.test_time_label = ctk.CTkLabel(
            self,
            text="Test time (sec)",
            font=STD_FONT,
            text_color=("black", "white"),
            # fg_color="gray",
        )
        self.test_time_label.grid(
            row=2, column=0, padx=10, pady=(5, 10), ipadx=5, sticky="ne"
        )

        self.test_time_var = StringVar(value="60")  # It would be more natural to use IntVar, but it triggers a Tcl-Tk exception when fetching this value with .get()
        self.test_time = ctk.CTkEntry(
            self, textvariable=self.test_time_var, width=70, justify="center"
        )
        self.test_time.grid(row=2, column=1, padx=10, pady=(5, 10), sticky="nw")

        # Start / Stop test buttons
        self.start_test_btn = ctk.CTkButton(
            self, text="Start Test", height=40, command=start_callback
        )
        self.start_test_btn.grid(row=3, column=1, padx=10, pady=(0, 10), sticky="sw")

        self.stop_test_btn = ctk.CTkButton(
            self, text="Stop Test", height=40, command=stop_callback
        )
        self.stop_test_btn.grid(row=4, column=1, padx=10, pady=10, sticky="nw")

    def difficulty_selected(self, event=None):
        self.main.load_sys_textbox()

    def read_text_file(self):
        if self.difficulty.get() == "Medium":
            source_file = "assets/Medium.txt"
        else:
            source_file = "assets/Hard.txt"
        with open(source_file, "r", encoding="utf-8") as file:
            file_content = file.read()
            paragraphs = [para.strip() for para in file_content.split("\n\n") if para.strip()]
        return random.choice(paragraphs)

    def update_test_number(self, num):
        update_title = f"Setup a new test: Test #{num}"
        self.test_number.set(update_title)


class TestResults(ctk.CTkFrame):
    def __init__(self, parent, details_callback):
        super().__init__(parent)

        STD_FONT = ctk.CTkFont("Arial", 12)
        BOLD_FONT = ctk.CTkFont("Arial", 16, "bold")

        self.grid(row=1, column=1, padx=10, pady=(10, 20), sticky="nsew")
        self.grid_rowconfigure(0, weight=2)
        self.grid_rowconfigure((1, 2, 3), weight=1, uniform="a")
        self.grid_columnconfigure((0, 1), weight=1, uniform="a")

        # Results frame label
        ctk.CTkLabel(
            self,
            text="Results from last completed test",
            font=BOLD_FONT,
            text_color=("black", "white"),
            # fg_color="gray",
        ).grid(
            row=0,
            column=0,
            padx=10,
            columnspan=2,
            pady=(10, 0),
            ipadx=10,
            ipady=2,
            sticky="nw",
        )

        # CPM result
        self.CPM_label = ctk.CTkLabel(
            self,
            text="CPM (chars per min)",
            font=STD_FONT,
            text_color=("black", "white"),
            # fg_color="gray",
        )
        self.CPM_label.grid(row=1, column=0, padx=10, pady=(10, 5), sticky="nse")

        self.CPM = ctk.CTkLabel(
            self,
            text="?",
            font=("Courier", 28, "bold"),
            text_color="gray",
            width=70,
            justify="right",
        )
        self.CPM.grid(row=1, column=1, padx=10, pady=(10, 5), sticky="nsw")

        # WPM result
        self.WPM_label = ctk.CTkLabel(
            self,
            text="WPM (words per min)",
            font=STD_FONT,
            text_color=("black", "white"),
            # fg_color="gray",
        )
        self.WPM_label.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="nse")

        self.WPM = ctk.CTkLabel(
            self,
            text="?",
            font=("Courier", 42, "bold"),
            text_color=("black", "white"),
            width=70,
            justify="right",
        )
        self.WPM.grid(row=2, column=1, padx=10, pady=(5, 10), sticky="nsw")

        # Result details button
        self.details_btn = ctk.CTkButton(
            self, text="Show details", height=40, command=details_callback
        )
        self.details_btn.grid(row=3, column=1, padx=10, pady=(10, 20), sticky="sw")


class ResultDetails(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)

        TITLE_FONT = ctk.CTkFont("Arial", 24, "bold")
        SUBTITLE_FONT = ctk.CTkFont("Arial", 14)
        LABEL_FONT = ctk.CTkFont("Arial", 12)
        RESULT_FONT = ctk.CTkFont("Courier", 36, "bold")
        WPM_FONT = ctk.CTkFont("Courier", 36, "bold")

        self.main = parent
        self.today = datetime.date.today()

        self.title("Test results")
        self.geometry("600x400+250+100")

        self.grid_rowconfigure((0, 1, 2), weight=1)
        self.grid_columnconfigure((0, 1), weight=1, uniform="a")

        ctk.CTkLabel(self, text="Your test results", font=TITLE_FONT).grid(
            row=0, column=0, columnspan=2, padx=30, pady=(20, 0), sticky="sw"
        )
        ctk.CTkLabel(
            self,
            text=f"Test #{self.main.test_number}  ·  {self.today.strftime("%A, %B %d, %Y")}",
            font=SUBTITLE_FONT,
        ).grid(row=1, column=0, columnspan=2, padx=30, pady=(0, 20), sticky="nw")

        # Left-side dataset
        left_dset = ctk.CTkFrame(self)
        left_dset.grid(row=2, column=0, padx=10, pady=20, sticky="ne")
        self.grid_rowconfigure((0, 1, 2), weight=1)  # , uniform="a")
        self.grid_columnconfigure((0, 1), weight=1)  # , uniform="a")

        # Raw char count
        ctk.CTkLabel(left_dset, text="Raw character count", font=LABEL_FONT).grid(
            row=0, column=0, padx=10, pady=5, sticky="nse"
        )
        self.raw_char_count = ctk.CTkLabel(
            left_dset, text="0", font=RESULT_FONT, justify="right"
        )
        self.raw_char_count.grid(row=0, column=1, padx=10, pady=5, sticky="nsw")

        # Error count
        ctk.CTkLabel(left_dset, text="Error count", font=LABEL_FONT).grid(
            row=1, column=0, padx=10, pady=5, sticky="nse"
        )
        self.error_count = ctk.CTkLabel(
            left_dset, text="0", font=RESULT_FONT, justify="right"
        )
        self.error_count.grid(row=1, column=1, padx=10, pady=5, sticky="nsw")

        # Effective test time
        ctk.CTkLabel(left_dset, text="Effective test time (sec)", font=LABEL_FONT).grid(
            row=2, column=0, padx=10, pady=5, sticky="nse"
        )
        self.test_time = ctk.CTkLabel(
            left_dset, text="0", font=RESULT_FONT, justify="right"
        )
        self.test_time.grid(row=2, column=1, padx=10, pady=5, sticky="nsw")

        # Right-side dataset
        right_dset = ctk.CTkFrame(self)
        right_dset.grid(row=2, column=1, padx=10, pady=20, sticky="nw")
        self.grid_rowconfigure((0, 1, 2), weight=1)  # , uniform="a")
        self.grid_columnconfigure((0, 1), weight=1)  # , uniform="a")

        # CPM
        ctk.CTkLabel(right_dset, text="CPM", font=LABEL_FONT).grid(
            row=0, column=0, padx=10, pady=5, sticky="nse"
        )
        self.CPM = ctk.CTkLabel(right_dset, text="0", font=RESULT_FONT, justify="right")
        self.CPM.grid(row=0, column=1, padx=10, pady=5, sticky="nsw")

        # WPM
        ctk.CTkLabel(right_dset, text="WPM", font=LABEL_FONT).grid(
            row=1, column=0, padx=10, pady=5, sticky="nse"
        )
        self.WPM = ctk.CTkLabel(right_dset, text="0", font=WPM_FONT, justify="right")
        self.WPM.grid(row=1, column=1, padx=10, pady=5, sticky="nsw")

        # Accuracy
        ctk.CTkLabel(right_dset, text="Accuracy", font=LABEL_FONT).grid(
            row=2, column=0, padx=10, pady=5, sticky="nse"
        )
        self.accuracy = ctk.CTkLabel(
            right_dset, text="0.0%", font=RESULT_FONT, justify="right"
        )
        self.accuracy.grid(row=2, column=1, padx=10, pady=5, sticky="nsw")

        ctk.CTkButton(self, height=40, text="Close", command=self.close_popup).grid(
            row=3, column=1, padx=20, pady=20, sticky="se"
        )

        self.withdraw()  # Until the "Show details" button is clicked (again)
        self.protocol("WM_DELETE_WINDOW", self.close_popup)

    def close_popup(self):
        self.grab_release()
        self.destroy()


if __name__ == "__main__":
    main()
