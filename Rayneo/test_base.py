from kivy.app import App
from kivy.uix.label import Label

class TestApp(App):
    def build(self):
        return Label(text="Se vedi questo, Kivy funziona!")

if __name__ == '__main__':
    TestApp().run()