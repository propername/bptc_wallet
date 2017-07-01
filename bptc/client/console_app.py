import sys

import bptc.networking.utils as network_utils
from main import __version__
import bptc
from bptc.utils.interactive_shell import InteractiveShell
from bptc.data.hashgraph import init_hashgraph
from bptc.data.db import DB

class ConsoleApp(InteractiveShell):
    def __init__(self, cl_args):
        self.cl_args = cl_args
        self.commands = dict(
            push=dict(
                help='Send local hashgraph to another client',
                args=[
                    (['target'], dict(default='localhost:8000', nargs='?',
                     help='Target address (incl. port)'))
                ],
            ),
            push_random=dict(
                help='Start pushing to randomly chosen clients',
            ),
            register=dict(
                help='Register this hashgraph member at the registry',
                args=[
                    (['target'], dict(default=self.cl_args.register,
                     nargs='?', help='Registry address (incl. port)'))
                ],
            ),
            query_members=dict(
                help='Query network members from registry',
                args=[
                    (['target'], dict(default=self.cl_args.query_members,
                     nargs='?', help='Registry address (incl. port)'))
                ],
            ),
        )
        super().__init__('BPTC Wallet {} CLI'.format(__version__))
        self.me = None
        self.hashgraph = None
        self.network = None
        init_hashgraph(self)

    def __call__(self):
        try:
            network_utils.initial_checks(self)
            super().__call__()
        finally:
            bptc.logger.info("Stopping...")
            DB.save(self.network.hashgraph)
            network_utils.stop_reactor_thread()
        # TODO: If no command was entered and Ctrl+C was hit, the process doesn't stop

    # --------------------------------------------------------------------------
    # Hashgraph actions
    # --------------------------------------------------------------------------

    def cmd_register(self, args):
        ip, port = args.target.split(':')
        network_utils.register(self.me.id, self.cl_args.port, ip, port)

    def cmd_query_members(self, args):
        ip, port = args.target.split(':')
        network_utils.query_members(self, ip, port)

    def cmd_heartbeat(self, args):
        pass

    def cmd_push(self, args):
        ip, port = args.target.split(':')
        self.network.push_to(ip, int(port))

    def cmd_push_random(self, args):
        self.network.start_background_pushes()
