#!/usr/bin/env python
"""

Copyright (c) 2020-2023 Alex Forencich

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

"""

import itertools
import logging
import struct
import os

from scapy.layers.l2 import Ether

import pytest
import cocotb_test.simulator

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.utils import get_time_from_sim_steps
from cocotb.regression import TestFactory

from cocotbext.eth import GmiiFrame, GmiiSource, GmiiSink, PtpClockSimTime
from cocotbext.axi import AxiStreamBus, AxiStreamSource, AxiStreamSink, AxiStreamFrame
from cocotbext.axi.stream import define_stream


PtpTsBus, PtpTsTransaction, PtpTsSource, PtpTsSink, PtpTsMonitor = define_stream("PtpTs",
    signals=["ts", "ts_valid"],
    optional_signals=["ts_tag", "ts_ready"]
)


class TB:
    def __init__(self, dut):
        self.dut = dut

        self.log = logging.getLogger("cocotb.tb")
        self.log.setLevel(logging.DEBUG)

        self._enable_generator_rx = None
        self._enable_generator_tx = None
        self._enable_cr_rx = None
        self._enable_cr_tx = None

        cocotb.start_soon(Clock(dut.rx_clk, 8, units="ns").start())
        cocotb.start_soon(Clock(dut.tx_clk, 8, units="ns").start())

        self.gmii_source = GmiiSource(dut.gmii_rxd, dut.gmii_rx_er, dut.gmii_rx_dv,
            dut.rx_clk, dut.rx_rst, dut.rx_clk_enable, dut.rx_mii_select)
        self.gmii_sink = GmiiSink(dut.gmii_txd, dut.gmii_tx_er, dut.gmii_tx_en,
            dut.tx_clk, dut.tx_rst, dut.tx_clk_enable, dut.tx_mii_select)

        self.axis_source = AxiStreamSource(AxiStreamBus.from_prefix(dut, "tx_axis"), dut.tx_clk, dut.tx_rst)
        self.axis_sink = AxiStreamSink(AxiStreamBus.from_prefix(dut, "rx_axis"), dut.rx_clk, dut.rx_rst)

        self.rx_ptp_clock = PtpClockSimTime(ts_64=dut.rx_ptp_ts, clock=dut.rx_clk)
        self.tx_ptp_clock = PtpClockSimTime(ts_64=dut.tx_ptp_ts, clock=dut.tx_clk)
        self.tx_ptp_ts_sink = PtpTsSink(PtpTsBus.from_prefix(dut, "tx_axis_ptp"), dut.tx_clk, dut.tx_rst)

        dut.tx_lfc_req.setimmediatevalue(0)
        dut.tx_lfc_resend.setimmediatevalue(0)
        dut.rx_lfc_en.setimmediatevalue(0)
        dut.rx_lfc_ack.setimmediatevalue(0)

        dut.tx_pfc_req.setimmediatevalue(0)
        dut.tx_pfc_resend.setimmediatevalue(0)
        dut.rx_pfc_en.setimmediatevalue(0)
        dut.rx_pfc_ack.setimmediatevalue(0)

        dut.tx_lfc_pause_en.setimmediatevalue(0)
        dut.tx_pause_req.setimmediatevalue(0)

        dut.rx_clk_enable.setimmediatevalue(1)
        dut.tx_clk_enable.setimmediatevalue(1)
        dut.rx_mii_select.setimmediatevalue(0)
        dut.tx_mii_select.setimmediatevalue(0)

        dut.ifg_delay.setimmediatevalue(0)
        dut.cfg_mcf_rx_eth_dst_mcast.setimmediatevalue(0)
        dut.cfg_mcf_rx_check_eth_dst_mcast.setimmediatevalue(0)
        dut.cfg_mcf_rx_eth_dst_ucast.setimmediatevalue(0)
        dut.cfg_mcf_rx_check_eth_dst_ucast.setimmediatevalue(0)
        dut.cfg_mcf_rx_eth_src.setimmediatevalue(0)
        dut.cfg_mcf_rx_check_eth_src.setimmediatevalue(0)
        dut.cfg_mcf_rx_eth_type.setimmediatevalue(0)
        dut.cfg_mcf_rx_opcode_lfc.setimmediatevalue(0)
        dut.cfg_mcf_rx_check_opcode_lfc.setimmediatevalue(0)
        dut.cfg_mcf_rx_opcode_pfc.setimmediatevalue(0)
        dut.cfg_mcf_rx_check_opcode_pfc.setimmediatevalue(0)
        dut.cfg_mcf_rx_forward.setimmediatevalue(0)
        dut.cfg_mcf_rx_enable.setimmediatevalue(0)
        dut.cfg_tx_lfc_eth_dst.setimmediatevalue(0)
        dut.cfg_tx_lfc_eth_src.setimmediatevalue(0)
        dut.cfg_tx_lfc_eth_type.setimmediatevalue(0)
        dut.cfg_tx_lfc_opcode.setimmediatevalue(0)
        dut.cfg_tx_lfc_en.setimmediatevalue(0)
        dut.cfg_tx_lfc_quanta.setimmediatevalue(0)
        dut.cfg_tx_lfc_refresh.setimmediatevalue(0)
        dut.cfg_tx_pfc_eth_dst.setimmediatevalue(0)
        dut.cfg_tx_pfc_eth_src.setimmediatevalue(0)
        dut.cfg_tx_pfc_eth_type.setimmediatevalue(0)
        dut.cfg_tx_pfc_opcode.setimmediatevalue(0)
        dut.cfg_tx_pfc_en.setimmediatevalue(0)
        dut.cfg_tx_pfc_quanta.setimmediatevalue(0)
        dut.cfg_tx_pfc_refresh.setimmediatevalue(0)
        dut.cfg_rx_lfc_opcode.setimmediatevalue(0)
        dut.cfg_rx_lfc_en.setimmediatevalue(0)
        dut.cfg_rx_pfc_opcode.setimmediatevalue(0)
        dut.cfg_rx_pfc_en.setimmediatevalue(0)

    async def reset(self):
        self.dut.rx_rst.setimmediatevalue(0)
        self.dut.tx_rst.setimmediatevalue(0)
        await RisingEdge(self.dut.tx_clk)
        await RisingEdge(self.dut.tx_clk)
        self.dut.rx_rst.value = 1
        self.dut.tx_rst.value = 1
        await RisingEdge(self.dut.tx_clk)
        await RisingEdge(self.dut.tx_clk)
        self.dut.rx_rst.value = 0
        self.dut.tx_rst.value = 0
        await RisingEdge(self.dut.tx_clk)
        await RisingEdge(self.dut.tx_clk)

    def set_enable_generator_rx(self, generator=None):
        if self._enable_cr_rx is not None:
            self._enable_cr_rx.kill()
            self._enable_cr_rx = None

        self._enable_generator_rx = generator

        if self._enable_generator_rx is not None:
            self._enable_cr_rx = cocotb.start_soon(self._run_enable_rx())

    def set_enable_generator_tx(self, generator=None):
        if self._enable_cr_tx is not None:
            self._enable_cr_tx.kill()
            self._enable_cr_tx = None

        self._enable_generator_tx = generator

        if self._enable_generator_tx is not None:
            self._enable_cr_tx = cocotb.start_soon(self._run_enable_tx())

    def clear_enable_generator_rx(self):
        self.set_enable_generator_rx(None)

    def clear_enable_generator_tx(self):
        self.set_enable_generator_tx(None)

    async def _run_enable_rx(self):
        for val in self._enable_generator_rx:
            self.dut.rx_clk_enable.value = val
            await RisingEdge(self.dut.rx_clk)

    async def _run_enable_tx(self):
        for val in self._enable_generator_tx:
            self.dut.tx_clk_enable.value = val
            await RisingEdge(self.dut.tx_clk)


async def run_test_rx(dut, payload_lengths=None, payload_data=None, ifg=12, enable_gen=None, mii_sel=False):

    tb = TB(dut)

    tb.gmii_source.ifg = ifg
    tb.dut.ifg_delay.value = ifg
    tb.dut.rx_mii_select.value = mii_sel
    tb.dut.tx_mii_select.value = mii_sel

    if enable_gen is not None:
        tb.set_enable_generator_rx(enable_gen())
        tb.set_enable_generator_tx(enable_gen())

    await tb.reset()

    test_frames = [payload_data(x) for x in payload_lengths()]
    tx_frames = []

    for test_data in test_frames:
        test_frame = GmiiFrame.from_payload(test_data, tx_complete=tx_frames.append)
        await tb.gmii_source.send(test_frame)

    for test_data in test_frames:
        rx_frame = await tb.axis_sink.recv()
        tx_frame = tx_frames.pop(0)

        frame_error = rx_frame.tuser & 1
        ptp_ts = rx_frame.tuser >> 1
        ptp_ts_ns = ptp_ts / 2**16

        tx_frame_sfd_ns = get_time_from_sim_steps(tx_frame.sim_time_sfd, "ns")

        tb.log.info("RX frame PTP TS: %f ns", ptp_ts_ns)
        tb.log.info("TX frame SFD sim time: %f ns", tx_frame_sfd_ns)

        assert rx_frame.tdata == test_data
        assert frame_error == 0
        assert abs(ptp_ts_ns - tx_frame_sfd_ns - (32 if enable_gen else 8)) < 0.01

    assert tb.axis_sink.empty()

    await RisingEdge(dut.rx_clk)
    await RisingEdge(dut.rx_clk)


async def run_test_tx(dut, payload_lengths=None, payload_data=None, ifg=12, enable_gen=None, mii_sel=False):

    tb = TB(dut)

    tb.gmii_source.ifg = ifg
    tb.dut.ifg_delay.value = ifg
    tb.dut.rx_mii_select.value = mii_sel
    tb.dut.tx_mii_select.value = mii_sel

    if enable_gen is not None:
        tb.set_enable_generator_rx(enable_gen())
        tb.set_enable_generator_tx(enable_gen())

    await tb.reset()

    test_frames = [payload_data(x) for x in payload_lengths()]

    for test_data in test_frames:
        await tb.axis_source.send(AxiStreamFrame(test_data, tuser=2))

    for test_data in test_frames:
        rx_frame = await tb.gmii_sink.recv()
        ptp_ts = await tb.tx_ptp_ts_sink.recv()

        ptp_ts_ns = int(ptp_ts.ts) / 2**16

        rx_frame_sfd_ns = get_time_from_sim_steps(rx_frame.sim_time_sfd, "ns")

        tb.log.info("TX frame PTP TS: %f ns", ptp_ts_ns)
        tb.log.info("RX frame SFD sim time: %f ns", rx_frame_sfd_ns)

        assert rx_frame.get_payload() == test_data
        assert rx_frame.check_fcs()
        assert rx_frame.error is None
        assert abs(rx_frame_sfd_ns - ptp_ts_ns - (32 if enable_gen else 8)) < 0.01

    assert tb.gmii_sink.empty()

    await RisingEdge(dut.tx_clk)
    await RisingEdge(dut.tx_clk)


async def run_test_lfc(dut, ifg=12, enable_gen=None, mii_sel=True):

    tb = TB(dut)

    tb.gmii_source.ifg = ifg
    tb.dut.ifg_delay.value = ifg
    tb.dut.rx_mii_select.value = mii_sel
    tb.dut.tx_mii_select.value = mii_sel

    if enable_gen is not None:
        tb.set_enable_generator_rx(enable_gen())
        tb.set_enable_generator_tx(enable_gen())

    await tb.reset()

    dut.tx_lfc_req.value = 0
    dut.tx_lfc_resend.value = 0
    dut.rx_lfc_en.value = 1
    dut.rx_lfc_ack.value = 0

    dut.tx_lfc_pause_en.value = 1
    dut.tx_pause_req.value = 0

    dut.cfg_mcf_rx_eth_dst_mcast.value = 0x0180C2000001
    dut.cfg_mcf_rx_check_eth_dst_mcast.value = 1
    dut.cfg_mcf_rx_eth_dst_ucast.value = 0xDAD1D2D3D4D5
    dut.cfg_mcf_rx_check_eth_dst_ucast.value = 0
    dut.cfg_mcf_rx_eth_src.value = 0x5A5152535455
    dut.cfg_mcf_rx_check_eth_src.value = 0
    dut.cfg_mcf_rx_eth_type.value = 0x8808
    dut.cfg_mcf_rx_opcode_lfc.value = 0x0001
    dut.cfg_mcf_rx_check_opcode_lfc.value = 1
    dut.cfg_mcf_rx_opcode_pfc.value = 0x0101
    dut.cfg_mcf_rx_check_opcode_pfc.value = 1

    dut.cfg_mcf_rx_forward.value = 0
    dut.cfg_mcf_rx_enable.value = 1

    dut.cfg_tx_lfc_eth_dst.value = 0x0180C2000001
    dut.cfg_tx_lfc_eth_src.value = 0x5A5152535455
    dut.cfg_tx_lfc_eth_type.value = 0x8808
    dut.cfg_tx_lfc_opcode.value = 0x0001
    dut.cfg_tx_lfc_en.value = 1
    dut.cfg_tx_lfc_quanta.value = 0xFFFF
    dut.cfg_tx_lfc_refresh.value = 0x7F00

    dut.cfg_rx_lfc_opcode.value = 0x0001
    dut.cfg_rx_lfc_en.value = 1

    test_tx_pkts = []
    test_rx_pkts = []

    for k in range(32):
        length = 128
        payload = bytearray(itertools.islice(itertools.cycle(range(256)), length))

        eth = Ether(src='5A:51:52:53:54:55', dst='DA:D1:D2:D3:D4:D5', type=0x8000)
        test_pkt = eth / payload
        test_tx_pkts.append(test_pkt.copy())

        await tb.axis_source.send(bytes(test_pkt))

        eth = Ether(src='DA:D1:D2:D3:D4:D5', dst='5A:51:52:53:54:55', type=0x8000)
        test_pkt = eth / payload
        test_rx_pkts.append(test_pkt.copy())

        test_frame = GmiiFrame.from_payload(bytes(test_pkt))
        await tb.gmii_source.send(test_frame)

        if k == 16:
            eth = Ether(src='DA:D1:D2:D3:D4:D5', dst='01:80:C2:00:00:01', type=0x8808)
            test_pkt = eth / struct.pack('!HH', 0x0001, 100)
            test_rx_pkts.append(test_pkt.copy())

            test_frame = GmiiFrame.from_payload(bytes(test_pkt))
            await tb.gmii_source.send(test_frame)

    for k in range(1000):
        await RisingEdge(dut.tx_clk)

    dut.tx_lfc_req.value = 1

    for k in range(1000):
        await RisingEdge(dut.tx_clk)

    dut.tx_lfc_req.value = 0

    while not dut.rx_lfc_req.value.integer:
        await RisingEdge(dut.tx_clk)

    for k in range(1000):
        await RisingEdge(dut.tx_clk)

    dut.tx_lfc_req.value = 1

    for k in range(1000):
        await RisingEdge(dut.tx_clk)

    dut.tx_lfc_req.value = 0

    while test_rx_pkts:
        rx_frame = await tb.axis_sink.recv()

        rx_pkt = Ether(bytes(rx_frame))

        tb.log.info("RX packet: %s", repr(rx_pkt))

        if rx_pkt.type == 0x8808:
            test_pkt = test_rx_pkts.pop(0)
            # check prefix as frame gets zero-padded
            assert bytes(rx_pkt).find(bytes(test_pkt)) == 0
            if isinstance(rx_frame.tuser, list):
                assert rx_frame.tuser[-1] & 1
            else:
                assert rx_frame.tuser & 1
        else:
            test_pkt = test_rx_pkts.pop(0)
            # check prefix as frame gets zero-padded
            assert bytes(rx_pkt).find(bytes(test_pkt)) == 0
            if isinstance(rx_frame.tuser, list):
                assert not rx_frame.tuser[-1] & 1
            else:
                assert not rx_frame.tuser & 1

    tx_lfc_cnt = 0

    while test_tx_pkts:
        tx_frame = await tb.gmii_sink.recv()

        tx_pkt = Ether(bytes(tx_frame.get_payload()))

        tb.log.info("TX packet: %s", repr(tx_pkt))

        if tx_pkt.type == 0x8808:
            tx_lfc_cnt += 1
        else:
            test_pkt = test_tx_pkts.pop(0)
            # check prefix as frame gets zero-padded
            assert bytes(tx_pkt).find(bytes(test_pkt)) == 0

    assert tx_lfc_cnt == 4

    assert tb.axis_sink.empty()
    assert tb.gmii_sink.empty()

    await RisingEdge(dut.tx_clk)
    await RisingEdge(dut.tx_clk)


async def run_test_pfc(dut, ifg=12, enable_gen=None, mii_sel=True):

    tb = TB(dut)

    tb.gmii_source.ifg = ifg
    tb.dut.ifg_delay.value = ifg
    tb.dut.rx_mii_select.value = mii_sel
    tb.dut.tx_mii_select.value = mii_sel

    if enable_gen is not None:
        tb.set_enable_generator_rx(enable_gen())
        tb.set_enable_generator_tx(enable_gen())

    await tb.reset()

    dut.tx_pfc_req.value = 0x00
    dut.tx_pfc_resend.value = 0
    dut.rx_pfc_en.value = 0xff
    dut.rx_pfc_ack.value = 0

    dut.tx_lfc_pause_en.value = 0
    dut.tx_pause_req.value = 0

    dut.cfg_mcf_rx_eth_dst_mcast.value = 0x0180C2000001
    dut.cfg_mcf_rx_check_eth_dst_mcast.value = 1
    dut.cfg_mcf_rx_eth_dst_ucast.value = 0xDAD1D2D3D4D5
    dut.cfg_mcf_rx_check_eth_dst_ucast.value = 0
    dut.cfg_mcf_rx_eth_src.value = 0x5A5152535455
    dut.cfg_mcf_rx_check_eth_src.value = 0
    dut.cfg_mcf_rx_eth_type.value = 0x8808
    dut.cfg_mcf_rx_opcode_lfc.value = 0x0001
    dut.cfg_mcf_rx_check_opcode_lfc.value = 1
    dut.cfg_mcf_rx_opcode_pfc.value = 0x0101
    dut.cfg_mcf_rx_check_opcode_pfc.value = 1

    dut.cfg_mcf_rx_forward.value = 0
    dut.cfg_mcf_rx_enable.value = 1

    dut.cfg_tx_pfc_eth_dst.value = 0x0180C2000001
    dut.cfg_tx_pfc_eth_src.value = 0x5A5152535455
    dut.cfg_tx_pfc_eth_type.value = 0x8808
    dut.cfg_tx_pfc_opcode.value = 0x0101
    dut.cfg_tx_pfc_en.value = 1
    dut.cfg_tx_pfc_quanta.value = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
    dut.cfg_tx_pfc_refresh.value = 0x7F007F007F007F007F007F007F007F00

    dut.cfg_rx_pfc_opcode.value = 0x0101
    dut.cfg_rx_pfc_en.value = 1

    test_tx_pkts = []
    test_rx_pkts = []

    for k in range(32):
        length = 128
        payload = bytearray(itertools.islice(itertools.cycle(range(256)), length))

        eth = Ether(src='5A:51:52:53:54:55', dst='DA:D1:D2:D3:D4:D5', type=0x8000)
        test_pkt = eth / payload
        test_tx_pkts.append(test_pkt.copy())

        await tb.axis_source.send(bytes(test_pkt))

        eth = Ether(src='DA:D1:D2:D3:D4:D5', dst='5A:51:52:53:54:55', type=0x8000)
        test_pkt = eth / payload
        test_rx_pkts.append(test_pkt.copy())

        test_frame = GmiiFrame.from_payload(bytes(test_pkt))
        await tb.gmii_source.send(test_frame)

        if k == 16:
            eth = Ether(src='DA:D1:D2:D3:D4:D5', dst='01:80:C2:00:00:01', type=0x8808)
            test_pkt = eth / struct.pack('!HH8H', 0x0101, 0x00FF, 10, 20, 30, 40, 50, 60, 70, 80)
            test_rx_pkts.append(test_pkt.copy())

            test_frame = GmiiFrame.from_payload(bytes(test_pkt))
            await tb.gmii_source.send(test_frame)

    for i in range(8):
        for k in range(500):
            await RisingEdge(dut.tx_clk)

        dut.tx_pfc_req.value = 0xff >> (7-i)

    for k in range(500):
        await RisingEdge(dut.tx_clk)

    dut.tx_pfc_req.value = 0x00

    while test_rx_pkts:
        rx_frame = await tb.axis_sink.recv()

        rx_pkt = Ether(bytes(rx_frame))

        tb.log.info("RX packet: %s", repr(rx_pkt))

        if rx_pkt.type == 0x8808:
            test_pkt = test_rx_pkts.pop(0)
            # check prefix as frame gets zero-padded
            assert bytes(rx_pkt).find(bytes(test_pkt)) == 0
            if isinstance(rx_frame.tuser, list):
                assert rx_frame.tuser[-1] & 1
            else:
                assert rx_frame.tuser & 1
        else:
            test_pkt = test_rx_pkts.pop(0)
            # check prefix as frame gets zero-padded
            assert bytes(rx_pkt).find(bytes(test_pkt)) == 0
            if isinstance(rx_frame.tuser, list):
                assert not rx_frame.tuser[-1] & 1
            else:
                assert not rx_frame.tuser & 1

    tx_pfc_cnt = 0

    while test_tx_pkts:
        tx_frame = await tb.gmii_sink.recv()

        tx_pkt = Ether(bytes(tx_frame.get_payload()))

        tb.log.info("TX packet: %s", repr(tx_pkt))

        if tx_pkt.type == 0x8808:
            tx_pfc_cnt += 1
        else:
            test_pkt = test_tx_pkts.pop(0)
            # check prefix as frame gets zero-padded
            assert bytes(tx_pkt).find(bytes(test_pkt)) == 0

    assert tx_pfc_cnt > 2 and tx_pfc_cnt <= 9

    assert tb.axis_sink.empty()
    assert tb.gmii_sink.empty()

    await RisingEdge(dut.tx_clk)
    await RisingEdge(dut.tx_clk)


def size_list():
    return list(range(60, 128)) + [512, 1514] + [60]*10


def incrementing_payload(length):
    return bytearray(itertools.islice(itertools.cycle(range(256)), length))


def cycle_en():
    return itertools.cycle([0, 0, 0, 1])


if cocotb.SIM_NAME:

    for test in [run_test_rx, run_test_tx]:

        factory = TestFactory(test)
        factory.add_option("payload_lengths", [size_list])
        factory.add_option("payload_data", [incrementing_payload])
        factory.add_option("ifg", [12])
        factory.add_option("enable_gen", [None, cycle_en])
        factory.add_option("mii_sel", [False, True])
        factory.generate_tests()

    if cocotb.top.PFC_ENABLE.value:
        for test in [run_test_lfc, run_test_pfc]:
            factory = TestFactory(test)
            factory.add_option("ifg", [12])
            factory.add_option("enable_gen", [None, cycle_en])
            factory.add_option("mii_sel", [False, True])
            factory.generate_tests()


# cocotb-test

tests_dir = os.path.abspath(os.path.dirname(__file__))
rtl_dir = os.path.abspath(os.path.join(tests_dir, '..', '..', 'rtl'))
lib_dir = os.path.abspath(os.path.join(rtl_dir, '..', 'lib'))
axis_rtl_dir = os.path.abspath(os.path.join(lib_dir, 'axis', 'rtl'))


@pytest.mark.parametrize("pfc_en", [1, 0])
def test_eth_mac_1g(request, pfc_en):
    dut = "eth_mac_1g"
    module = os.path.splitext(os.path.basename(__file__))[0]
    toplevel = dut

    verilog_sources = [
        os.path.join(rtl_dir, f"{dut}.v"),
        os.path.join(rtl_dir, "axis_gmii_rx.v"),
        os.path.join(rtl_dir, "axis_gmii_tx.v"),
        os.path.join(rtl_dir, "mac_ctrl_rx.v"),
        os.path.join(rtl_dir, "mac_ctrl_tx.v"),
        os.path.join(rtl_dir, "mac_pause_ctrl_rx.v"),
        os.path.join(rtl_dir, "mac_pause_ctrl_tx.v"),
        os.path.join(rtl_dir, "lfsr.v"),
    ]

    parameters = {}

    parameters['DATA_WIDTH'] = 8
    parameters['ENABLE_PADDING'] = 1
    parameters['MIN_FRAME_LENGTH'] = 64
    parameters['TX_PTP_TS_ENABLE'] = 1
    parameters['TX_PTP_TS_WIDTH'] = 96
    parameters['TX_PTP_TS_CTRL_IN_TUSER'] = parameters['TX_PTP_TS_ENABLE']
    parameters['TX_PTP_TAG_ENABLE'] = parameters['TX_PTP_TS_ENABLE']
    parameters['TX_PTP_TAG_WIDTH'] = 16
    parameters['RX_PTP_TS_ENABLE'] = parameters['TX_PTP_TS_ENABLE']
    parameters['RX_PTP_TS_WIDTH'] = 96
    parameters['TX_USER_WIDTH'] = ((parameters['TX_PTP_TAG_WIDTH'] if parameters['TX_PTP_TAG_ENABLE'] else 0) + (1 if parameters['TX_PTP_TS_CTRL_IN_TUSER'] else 0) if parameters['TX_PTP_TS_ENABLE'] else 0) + 1
    parameters['RX_USER_WIDTH'] = (parameters['RX_PTP_TS_WIDTH'] if parameters['RX_PTP_TS_ENABLE'] else 0) + 1
    parameters['PFC_ENABLE'] = pfc_en
    parameters['PAUSE_ENABLE'] = parameters['PFC_ENABLE']

    extra_env = {f'PARAM_{k}': str(v) for k, v in parameters.items()}

    sim_build = os.path.join(tests_dir, "sim_build",
        request.node.name.replace('[', '-').replace(']', ''))

    cocotb_test.simulator.run(
        python_search=[tests_dir],
        verilog_sources=verilog_sources,
        toplevel=toplevel,
        module=module,
        parameters=parameters,
        sim_build=sim_build,
        extra_env=extra_env,
    )
