#!/usr/bin/python
#
# Copyright 2015 The Cluster-Insight Authors. All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for collector/collector.py."""

# global imports
import json
import re
import types
import unittest

# local imports
import collector
import global_state
import utilities


# A regular expression that matches the 'timestamp' attribute and value
# in JSON data.
TIMESTAMP_REGEXP = '"timestamp": "[-0-9:.TZ]+"'


class TestCollector(unittest.TestCase):
  """Test harness."""

  def setUp(self):
    gs = global_state.GlobalState()
    gs.init_caches_and_synchronization()
    gs.set_testing(True)
    gs.set_logger(collector.app.logger)
    gs.set_num_workers(1)  # execute worker tasks sequentially
    collector.app.context_graph_global_state = gs
    self.app = collector.app.test_client()

  def compare_to_golden(self, ret_value, fname):
    """Compares the returned value to the golden (expected) value.

    The golden value is read from the file
    'testdata/<last element of fname>.output.json'.
    All timestamp attributes and their values are removed from the returned
    value and the golden value prior to comparing them.

    Args:
      ret_value: JSON output from the server.
      fname: the middle part of the file name containing the golden
        (expected) output from the server.
    Raises:
      AssertError if the sanitized golden data differs from the sanitized
      return value.
    """
    assert isinstance(ret_value, types.StringTypes)
    assert isinstance(fname, types.StringTypes)

    # Read the golden data (expected value).
    golden_fname = 'testdata/' + fname + '.output.json'
    f = open(golden_fname, 'r')
    golden_data = f.read()
    f.close()

    # Remove all timestamps from golden data and returned value.
    sanitized_golden_data = re.sub(TIMESTAMP_REGEXP, '', golden_data)
    sanitized_ret_value = re.sub(TIMESTAMP_REGEXP, '', ret_value)

    # Strip whitespaces of the sanitized strings, and replace multiple
    # whitespaces by a single space
    sanitized_golden_data = re.sub(r'\s+', ' ', sanitized_golden_data.strip())
    sanitized_ret_value = re.sub(r'\s+', ' ', sanitized_ret_value.strip())

    # Find the index of the first discrepancy between 'sanitized_golden_data'
    # and 'sanitized_ret_value'. If they are equal, the index will point at
    # the position after the last character in both strings.
    # DO NOT replace this code with:
    # self.assertEqual(sanitized_golden_data, sanitized_ret_value)
    # The current code prints the tail of the mismatched data, which helps
    # the human developer identify and comprehend the discrepancies.
    i = 0
    while (i < len(sanitized_golden_data)) and (i < len(sanitized_ret_value)):
      if sanitized_golden_data[i] != sanitized_ret_value[i]:
        break
      i += 1

    # The sanitized golden data must equal the sanitized
    # return value.
    self.assertEqual(sanitized_golden_data[i:], sanitized_ret_value[i:])

  def test_regexp(self):
    """Tests the TIMESTAMP_REGEXP against various timestamp formats."""
    self.assertEqual(
        '{}',
        re.sub(TIMESTAMP_REGEXP, '',
               '{"timestamp": "2015-03-17T02:00:41.918629"}'))
    self.assertEqual(
        '{}',
        re.sub(TIMESTAMP_REGEXP, '', '{"timestamp": "2015-02-23T03:13:29Z"}'))

  def test_home(self):
    ret_value = self.app.get('/')
    self.assertTrue('Returns this help message' in ret_value.data)

  def test_nodes(self):
    ret_value = self.app.get('/cluster/resources/nodes')
    self.compare_to_golden(ret_value.data, 'nodes')

  def test_pods(self):
    ret_value = self.app.get('/cluster/resources/pods')
    self.compare_to_golden(ret_value.data, 'pods')

  def test_services(self):
    ret_value = self.app.get('/cluster/resources/services')
    self.compare_to_golden(ret_value.data, 'services')

  def test_rcontrollers(self):
    ret_value = self.app.get('/cluster/resources/rcontrollers')
    self.compare_to_golden(ret_value.data, 'replicationcontrollers')

  def test_containers(self):
    ret_value = self.app.get('/cluster/resources/containers')
    self.compare_to_golden(ret_value.data, 'containers')

  def test_processes(self):
    ret_value = self.app.get('/cluster/resources/processes')
    self.compare_to_golden(ret_value.data, 'processes')

  def test_images(self):
    ret_value = self.app.get('/cluster/resources/images')
    self.compare_to_golden(ret_value.data, 'images')

  def count_resources(self, output, type_name):
    assert isinstance(output, types.DictType)
    assert isinstance(type_name, types.StringTypes)
    if not isinstance(output.get('resources'), types.ListType):
      return 0

    n = 0
    for r in output.get('resources'):
      assert utilities.is_wrapped_object(r)
      if r.get('type') == type_name:
        n += 1

    return n

  def count_relations(self, output, type_name):
    assert isinstance(output, types.DictType)
    assert isinstance(type_name, types.StringTypes)
    if not isinstance(output.get('relations'), types.ListType):
      return 0

    n = 0
    for r in output.get('relations'):
      assert isinstance(r, types.DictType)
      if r.get('type') == type_name:
        n += 1

    return n

  def verify_resources(self, result, start_time, end_time):
    assert isinstance(result, types.DictType)
    assert utilities.valid_string(start_time)
    assert utilities.valid_string(end_time)
    self.assertEqual(1, self.count_resources(result, 'Cluster'))
    self.assertEqual(3, self.count_resources(result, 'Node'))
    self.assertEqual(6, self.count_resources(result, 'Service'))
    # TODO(eran): the pods count does not include the pods running in the
    # master. Fix the count once we include pods that run in the master node.
    self.assertEqual(10, self.count_resources(result, 'Pod'))
    self.assertEqual(4, self.count_resources(result, 'Container'))
    self.assertEqual(7, self.count_resources(result, 'Process'))
    self.assertEqual(2, self.count_resources(result, 'Image'))
    self.assertEqual(3, self.count_resources(result, 'ReplicationController'))

    # Verify that all resources are valid wrapped objects.
    assert isinstance(result.get('resources'), types.ListType)
    for r in result['resources']:
      # all resources must be valid.
      assert utilities.is_wrapped_object(r)
      assert start_time <= r['timestamp'] <= end_time

  def test_resources(self):
    """Test the '/resources' endpoint."""
    start_time = utilities.now()
    ret_value = self.app.get('/cluster/resources')
    end_time = utilities.now()
    result = json.loads(ret_value.data)
    self.verify_resources(result, start_time, end_time)

    self.assertEqual(0, self.count_relations(result, 'contains'))
    self.assertEqual(0, self.count_relations(result, 'createdFrom'))
    self.assertEqual(0, self.count_relations(result, 'loadBalances'))
    self.assertEqual(0, self.count_relations(result, 'monitors'))
    self.assertEqual(0, self.count_relations(result, 'runs'))

    # The overall timestamp must be in the expected range.
    self.assertTrue(utilities.valid_string(result.get('timestamp')))
    self.assertTrue(start_time <= result['timestamp'] <= end_time)

    json_output = json.dumps(result, sort_keys=True)
    self.assertEqual(2, json_output.count('"alternateLabel": '))
    self.assertEqual(36, json_output.count('"createdBy": '))

  def test_cluster(self):
    """Test the '/cluster' endpoint."""
    start_time = utilities.now()
    # Execrcise the collector. Read data from golden files and compute
    # a context graph.
    ret_value = self.app.get('/cluster')
    end_time = utilities.now()
    result = json.loads(ret_value.data)
    self.verify_resources(result, start_time, end_time)

    self.assertEqual(23, self.count_relations(result, 'contains'))
    self.assertEqual(3, self.count_relations(result, 'createdFrom'))
    self.assertEqual(7, self.count_relations(result, 'loadBalances'))
    self.assertEqual(6, self.count_relations(result, 'monitors'))
    self.assertEqual(10, self.count_relations(result, 'runs'))

    # Verify that all relations contain a timestamp in the range
    # [start_time, end_time].
    self.assertTrue(isinstance(result.get('relations'), types.ListType))
    for r in result['relations']:
      self.assertTrue(isinstance(r, types.DictType))
      timestamp = r.get('timestamp')
      self.assertTrue(utilities.valid_string(timestamp))
      self.assertTrue(start_time <= timestamp <= end_time)

    # The overall timestamp must be in the expected range.
    self.assertTrue(utilities.valid_string(result.get('timestamp')))
    self.assertTrue(start_time <= result['timestamp'] <= end_time)

    json_output = json.dumps(result, sort_keys=True)
    self.assertEqual(2, json_output.count('"alternateLabel": '))
    self.assertEqual(85, json_output.count('"createdBy": '))

  def test_debug(self):
    """Test the '/debug' endpoint."""
    ret_value = self.app.get('/debug')
    self.compare_to_golden(ret_value.data, 'debug')

  def test_version(self):
    """Test the '/version' endpoint."""
    ret_value = self.app.get('/version')
    result = json.loads(ret_value.data)
    self.assertTrue(result.get('success'))
    version = result.get('version')
    self.assertTrue(isinstance(version, types.StringTypes))
    # The version string is temporarily broken because the
    # cluster-insight master cannot read from the local Docker daemon.
    # See issue https://github.com/google/cluster-insight/issues/76 .
    # self.assertEqual(
    #     'kubernetes/cluster-insight ac933439ec5a 2015-03-28T17:23:41', version)
    self.assertEqual('_unknown_', version)

  def test_healthz(self):
    """Test the '/healthz' endpoint."""
    ret_value = self.app.get('/healthz')
    result = json.loads(ret_value.data)
    self.assertTrue(result.get('success'))
    health = result.get('health')
    self.assertTrue(isinstance(health, types.StringTypes))
    self.assertEqual('OK', health)


if __name__ == '__main__':
  unittest.main()

