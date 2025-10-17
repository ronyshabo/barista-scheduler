from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.checkbox import CheckBox
from kivy.uix.widget import Widget
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.table import Table
from kivy.uix.table import TableRow
from kivy.uix.table import TableCell

import json
import os
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional
import re

# Set window size for mobile
Window.size = (400, 700)

class Employee:
    def __init__(self, name: str, base: float, aliases: List[str] = None, switch_override: Optional[str] = None):
        self.name = name
        self.base = base
        self.aliases = aliases or []
        self.switch_override = switch_override

def load_employees(path: str = "employees.json") -> List[Employee]:
    """Load employees from JSON file."""
    if not os.path.exists(path):
        # Create default employees if file doesn't exist
        default_employees = [
            {"name": "Youssef", "base": 15.0, "aliases": ["youssef", "yusuf"]},
            {"name": "Rony", "base": 15.0, "aliases": ["rony", "ron"]},
            {"name": "Kat", "base": 15.0, "aliases": ["kat", "katherine"]},
            {"name": "Daphne", "base": 15.0, "aliases": ["daphne", "daph"]}
        ]
        with open(path, 'w') as f:
            json.dump(default_employees, f, indent=2)
        return [Employee(**emp) for emp in default_employees]
    
    with open(path, 'r') as f:
        data = json.load(f)
    return [Employee(**emp) for emp in data]

class DateRangeSelector(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.spacing = 10
        self.padding = [20, 20, 20, 20]
        
        # Title
        title = Label(text='Barista Pay Calculator', size_hint_y=None, height=50, font_size=24, bold=True)
        self.add_widget(title)
        
        # Date range selection
        date_layout = GridLayout(cols=2, size_hint_y=None, height=100, spacing=10)
        
        date_layout.add_widget(Label(text='Start Date:', size_hint_x=0.3))
        self.start_date = TextInput(text=(date.today() - timedelta(days=7)).isoformat(), 
                                   size_hint_x=0.7, multiline=False)
        date_layout.add_widget(self.start_date)
        
        date_layout.add_widget(Label(text='End Date:', size_hint_x=0.3))
        self.end_date = TextInput(text=(date.today() + timedelta(days=1)).isoformat(), 
                                 size_hint_x=0.7, multiline=False)
        date_layout.add_widget(self.end_date)
        
        self.add_widget(date_layout)
        
        # Next button
        next_btn = Button(text='Next: Enter Tips', size_hint_y=None, height=50)
        next_btn.bind(on_press=self.on_next)
        self.add_widget(next_btn)
        
        # Add some spacing
        self.add_widget(Widget(size_hint_y=1))
    
    def on_next(self, instance):
        try:
            start_d = date.fromisoformat(self.start_date.text)
            end_d = date.fromisoformat(self.end_date.text)
            if end_d <= start_d:
                end_d = start_d + timedelta(days=1)
            
            # Switch to tip entry screen
            app = App.get_running_app()
            app.show_tip_entry(start_d, end_d)
        except ValueError:
            self.show_error("Invalid date format. Use YYYY-MM-DD")

    def show_error(self, message):
        popup = Popup(title='Error', content=Label(text=message), size_hint=(0.8, 0.4))
        popup.open()

class TipEntryScreen(BoxLayout):
    def __init__(self, start_date, end_date, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.spacing = 10
        self.padding = [20, 20, 20, 20]
        
        self.start_date = start_date
        self.end_date = end_date
        
        # Title
        title = Label(text=f'Enter Tips: {start_date} to {end_date}', 
                     size_hint_y=None, height=50, font_size=18, bold=True)
        self.add_widget(title)
        
        # Scrollable content
        scroll = ScrollView()
        content = BoxLayout(orientation='vertical', spacing=10, size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))
        
        # Generate date range
        self.tip_inputs = {}
        d = start_date
        while d < end_date:
            day_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=80, spacing=10)
            
            # Date label
            day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            day_name = day_names[d.weekday()]
            date_label = Label(text=f'{d.isoformat()}\n{day_name}', size_hint_x=0.4, font_size=14)
            day_layout.add_widget(date_label)
            
            # Opening tips
            open_layout = BoxLayout(orientation='vertical', size_hint_x=0.3)
            open_layout.add_widget(Label(text='Opening', size_hint_y=None, height=20, font_size=12))
            open_input = TextInput(text='0', multiline=False, size_hint_y=None, height=40)
            open_layout.add_widget(open_input)
            day_layout.add_widget(open_layout)
            
            # Closing tips
            close_layout = BoxLayout(orientation='vertical', size_hint_x=0.3)
            close_layout.add_widget(Label(text='Closing', size_hint_y=None, height=20, font_size=12))
            close_input = TextInput(text='0', multiline=False, size_hint_y=None, height=40)
            close_layout.add_widget(close_input)
            day_layout.add_widget(close_layout)
            
            self.tip_inputs[d.isoformat()] = {
                'open': open_input,
                'close': close_input
            }
            
            content.add_widget(day_layout)
            d += timedelta(days=1)
        
        scroll.add_widget(content)
        self.add_widget(scroll)
        
        # Buttons
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        back_btn = Button(text='Back', size_hint_x=0.5)
        back_btn.bind(on_press=self.on_back)
        btn_layout.add_widget(back_btn)
        
        compute_btn = Button(text='Compute Payouts', size_hint_x=0.5)
        compute_btn.bind(on_press=self.on_compute)
        btn_layout.add_widget(compute_btn)
        
        self.add_widget(btn_layout)
    
    def on_back(self, instance):
        app = App.get_running_app()
        app.show_date_selector()
    
    def on_compute(self, instance):
        # Collect tip data
        tip_data = {}
        for date_str, inputs in self.tip_inputs.items():
            try:
                open_tips = float(inputs['open'].text) if inputs['open'].text else 0.0
                close_tips = float(inputs['close'].text) if inputs['close'].text else 0.0
                tip_data[date_str] = {'open': open_tips, 'close': close_tips}
            except ValueError:
                self.show_error(f"Invalid tip amount for {date_str}")
                return
        
        # Show results
        app = App.get_running_app()
        app.show_results(tip_data)
    
    def show_error(self, message):
        popup = Popup(title='Error', content=Label(text=message), size_hint=(0.8, 0.4))
        popup.open()

class ResultsScreen(BoxLayout):
    def __init__(self, tip_data, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.spacing = 10
        self.padding = [20, 20, 20, 20]
        
        # Title
        title = Label(text='Payout Results', size_hint_y=None, height=50, font_size=20, bold=True)
        self.add_widget(title)
        
        # Summary
        total_tips = sum(data['open'] + data['close'] for data in tip_data.values())
        summary = Label(text=f'Total Tips: ${total_tips:.2f}\nDays: {len(tip_data)}', 
                       size_hint_y=None, height=80, font_size=16)
        self.add_widget(summary)
        
        # Schedule table
        schedule_label = Label(text='Schedule', size_hint_y=None, height=30, font_size=16, bold=True)
        self.add_widget(schedule_label)
        
        # Create schedule table
        scroll = ScrollView()
        table_layout = GridLayout(cols=6, size_hint_y=None, spacing=5)
        table_layout.bind(minimum_height=table_layout.setter('height'))
        
        # Headers
        headers = ['Date', 'Day', 'Youssef', 'Rony', 'Kat', 'Daphne']
        for header in headers:
            table_layout.add_widget(Label(text=header, size_hint_y=None, height=30, 
                                        font_size=12, bold=True, text_size=(None, None), 
                                        halign='center'))
        
        # Sample schedule data (you can enhance this with real schedule logic)
        employees = ['Youssef', 'Rony', 'Kat', 'Daphne']
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        for date_str, data in tip_data.items():
            d = date.fromisoformat(date_str)
            day_name = day_names[d.weekday()]
            
            # Date
            table_layout.add_widget(Label(text=date_str, size_hint_y=None, height=25, font_size=10))
            # Day
            table_layout.add_widget(Label(text=day_name, size_hint_y=None, height=25, font_size=10))
            
            # Sample schedule (you can enhance this with real logic)
            for emp in employees:
                if emp == 'Youssef':
                    schedule = 'O' if d.weekday() % 2 == 0 else 'C'
                elif emp == 'Rony':
                    schedule = 'C' if d.weekday() % 2 == 0 else 'O'
                else:
                    schedule = ''
                table_layout.add_widget(Label(text=schedule, size_hint_y=None, height=25, font_size=10))
        
        scroll.add_widget(table_layout)
        self.add_widget(scroll)
        
        # Back button
        back_btn = Button(text='Back to Start', size_hint_y=None, height=50)
        back_btn.bind(on_press=self.on_back)
        self.add_widget(back_btn)
    
    def on_back(self, instance):
        app = App.get_running_app()
        app.show_date_selector()

class BaristaPayApp(App):
    def build(self):
        self.title = 'Barista Pay Calculator'
        self.show_date_selector()
        return self.root
    
    def show_date_selector(self):
        self.root = DateRangeSelector()
    
    def show_tip_entry(self, start_date, end_date):
        self.root = TipEntryScreen(start_date, end_date)
    
    def show_results(self, tip_data):
        self.root = ResultsScreen(tip_data)

if __name__ == '__main__':
    BaristaPayApp().run()

