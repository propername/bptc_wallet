# -*- coding: utf-8 -*-
import threading
import os
from functools import partial
from time import sleep
from bokeh.io import curdoc
from bokeh.layouts import row, column
from bokeh.models import (Button, TextInput, ColumnDataSource, PanTool, HoverTool, Dimensions, PreText, WheelZoomTool)
from bokeh.palettes import plasma, small_palettes
from bokeh.plotting import figure
from twisted.internet import threads, reactor
from tornado import gen
from bptc import init_logger
from bptc.data.event import Fame
from bptc.protocols.pull_protocol import PullClientFactory

R_COLORS = small_palettes['Set2'][8]

doc = curdoc()

# shuffle(R_COLORS)
def round_color(r):
    return R_COLORS[r % 8]

I_COLORS = plasma(256)


class App:

    @staticmethod
    def start_reactor_thread():
        def start_reactor():
            reactor.run(installSignalHandlers=0)

        thread = threading.Thread(target=start_reactor)
        thread.daemon = True
        thread.start()
        print('Started reactor')

    def __init__(self):
        self.pull_thread = None
        log_directory = 'data/viz'
        os.makedirs(log_directory, exist_ok=True)
        init_logger(log_directory)

        if not reactor.running:
            self.start_reactor_thread()

        self.text = PreText(text='Reload the page to clear all events,\n'
                                 'especially when changing the member to\n'
                                 'pull from.',
                            width=500, height=100)
        self.ip_text_input = TextInput(value='localhost')
        self.port_text_input = TextInput(value='8001')
        self.start_pulling_button = Button(label="Start pulling...", width=60)
        self.start_pulling_button.on_click(partial(self.start_pulling, self.ip_text_input, self.port_text_input))
        self.stop_pulling_button = Button(label="Stop pulling...", width=60)
        self.stop_pulling_button.on_click(self.stop_pulling)

        self.all_events = {}
        self.new_events = {}
        self.verify_key_to_x = {}
        self.n_nodes = 10
        self.counter = 0

        plot = figure(
                plot_height=2000, plot_width=2000, y_range=(0, 30), x_range=(0, self.n_nodes - 1),
                tools=[PanTool(dimensions=[Dimensions.height, Dimensions.width]),
                       HoverTool(tooltips=[
                           ('id', '@id'), ('from', '@from'), ('height', '@height'), ('witness', '@witness'),
                           ('round', '@round'), ('data', '@data'), ('famous', '@famous'), ('round_received', '@round_received'),
                           ('consensus_timestamp', '@consensus_timestamp')])])
        plot.add_tools(WheelZoomTool())

        plot.xgrid.grid_line_color = None
        plot.xaxis.minor_tick_line_color = None
        plot.ygrid.grid_line_color = None
        plot.yaxis.minor_tick_line_color = None

        self.index_counter = 0
        self.links_src = ColumnDataSource(data={'x0': [], 'y0': [], 'x1': [],
                                                'y1': [], 'width': []})

        self.links_rend = plot.segment(color='#777777',
                x0='x0', y0='y0', x1='x1',
                y1='y1', source=self.links_src, line_width='width')

        self.events_src = ColumnDataSource(
                data={'x': [], 'y': [], 'round_color': [], 'line_alpha': [],
                      'round': [], 'id': [], 'payload': [], 'time': [], 'from': [], 'height': [], 'data': [],
                      'witness': [], 'famous': [], 'round_received': [], 'consensus_timestamp': []})

        self.events_rend = plot.circle(x='x', y='y', size=20, color='round_color',
                                       line_alpha='line_alpha', source=self.events_src, line_width=5)

        self.log = PreText(text='')

        control_column = column(self.text, self.ip_text_input,
                                self.port_text_input, self.start_pulling_button, self.stop_pulling_button, self.log)
        main_row = row([control_column, plot], sizing_mode='fixed')
        doc.add_root(main_row)

    @gen.coroutine
    def received_data_callback(self, from_member, events):
        for event_id, event in events.items():
            if event_id not in self.all_events:
                if event.verify_key not in self.verify_key_to_x.keys():
                    self.verify_key_to_x[event.verify_key] = self.counter
                    self.counter = self.counter + 1
                self.all_events[event_id] = event
                event.index = self.index_counter
                self.index_counter += 1
                self.new_events[event_id] = event
            else:
                self.update_event(event)
        self.n_nodes = len(self.verify_key_to_x)
        self.log.text += "Updated member {}...\n".format(from_member[:6])

    def update_event(self, event):
        index = self.all_events[event.id].index
        patches = {
            'round_color': [(index, self.color_of(event))],
            'famous': [(index, event.is_famous)],
            'round_received': [(index, event.round_received)],
            'consensus_timestamp': [(index, event.consensus_time)]
        }
        self.events_src.patch(patches)

    def start_pulling(self, ip_text_input, port_text_input):
        ip = ip_text_input.value
        port = int(port_text_input.value)
        factory = PullClientFactory(self, doc)

        self.pull_thread = PullingThread(ip, port, factory)
        self.pull_thread.daemon = True
        self.pull_thread.start()

    def stop_pulling(self):
        self.pull_thread.stop()

    @gen.coroutine
    def draw(self):
        events, links = self.extract_data(self.new_events)
        self.new_events = {}
        self.links_src.stream(links)
        self.events_src.stream(events)

    def extract_data(self, events):
        events_data = {'x': [], 'y': [], 'round_color': [], 'line_alpha': [], 'round': [], 'id': [], 'payload': [],
                       'time': [], 'from': [], 'height': [], 'data': [], 'witness': [], 'famous': [],
                       'round_received': [], 'consensus_timestamp': []}
        links_data = {'x0': [], 'y0': [], 'x1': [], 'y1': [], 'width': []}

        for event_id, event in events.items():
            x = self.verify_key_to_x[event.verify_key]
            y = event.height
            events_data['x'].append(x)
            events_data['y'].append(y)
            events_data['round_color'].append(self.color_of(event))
            events_data['round'].append(event.round)
            events_data['id'].append(event.id[:6] + "...")
            events_data['payload'].append("".format(event.data))
            events_data['time'].append(event.time)
            events_data['line_alpha'].append(1)
            events_data['from'].append(event.verify_key[:6] + '...')
            events_data['height'].append(event.height)
            events_data['data'].append('None' if event.data is None else str(event.data))
            events_data['witness'].append('Yes' if event.is_witness else 'No')
            events_data['famous'].append(event.is_famous)
            events_data['round_received'].append(event.round_received)
            events_data['consensus_timestamp'].append(event.consensus_time)

            if event.parents.self_parent is not None and event.parents.self_parent in self.all_events:
                links_data['x0'].append(x)
                links_data['y0'].append(y)
                links_data['x1'].append(str(self.verify_key_to_x[self.all_events[event.parents.self_parent].verify_key]))
                links_data['y1'].append(self.all_events[event.parents.self_parent].height)
                links_data['width'].append(3)
            else:
                print('{} is not in self.all_events'.format(str(event.parents.self_parent)))

            if event.parents.other_parent is not None and event.parents.other_parent in self.all_events:
                links_data['x0'].append(x)
                links_data['y0'].append(y)
                links_data['x1'].append(str(self.verify_key_to_x[self.all_events[event.parents.other_parent].verify_key]))
                links_data['y1'].append(self.all_events[event.parents.other_parent].height)
                links_data['width'].append(1)
            else:
                print('{} is not in self.all_events'.format(str(event.parents.other_parent)))

        return events_data, links_data

    @staticmethod
    def color_of(event):
        if event.round_received is not None:
            color = '#FF0000'
        elif event.is_famous == Fame.TRUE:
            color = '#000000'
        else:
            color = round_color(event.round)
        return color

App()


class PullingThread(threading.Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self, ip, port, factory):
        super(PullingThread, self).__init__()
        self.ip = ip
        self.port = port
        self.factory = factory
        self._stop_event = threading.Event()

    def run(self):
        while not self.stopped():
            threads.blockingCallFromThread(reactor, partial(reactor.connectTCP, self.ip, self.port, self.factory))
            sleep(0.5)

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()
